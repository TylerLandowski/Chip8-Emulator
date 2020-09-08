# Author: Tyler Landowski
# Reference:
# http://devernay.free.fr/hacks/chip8/C8TECH10.HTM

import os
import sys
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
from pygame.locals import *
from pygame.time import Clock
import typing
from random import randint
import numpy as np
import simpleaudio as sa
from time import sleep

# ----------------------------------------------------------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------------------------------------------------------

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED   = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE  = (0, 0, 255)
# Game
ROM = "ROM\\PONG"
# Display
SCALE         = 20
ON_COLOR      = GREEN
OFF_COLOR     = BLACK
# Keyboard
KEY = [-1] * 16
KEY[0x1], KEY[0x2], KEY[0x3], KEY[0xC] = K_1, K_2, K_3, K_4
KEY[0x4], KEY[0x5], KEY[0x6], KEY[0xD] = K_q, K_w, K_e, K_r
KEY[0x7], KEY[0x8], KEY[0x9], KEY[0xE] = K_a, K_s, K_d, K_f
KEY[0xA], KEY[0x0], KEY[0xB], KEY[0xF] = K_z, K_x, K_c, K_v
# Sound
SOUND_FREQUENCY = 400
# Speed (Delay timer frequency (Hz))
SPEED = 60
# Etc
DEBUG = False

# ----------------------------------------------------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------------------------------------------------

# Display
SCREEN_WIDTH  = 64
SCREEN_HEIGHT = 32
# i_ld Operation Modes
WAITKEY  = "K"   # Fx07 2=K
SPRITE   = "F"   # Fx29 1=F
BCD      = "B"   # Fx33 1=B
SAVEREG  = "[I]" # Fx55 1=[I]
LOADREG  = "[I]" # Fx65 2=[I]
SPRITES  = [
	[0xF0, 0x90, 0x90, 0x90, 0xF0], # 0
	[0x20, 0x60, 0x20, 0x20, 0x70], # 1
	[0xF0, 0x10, 0xF0, 0x80, 0xF0], # 2
	[0xF0, 0x10, 0xF0, 0x10, 0xF0], # 3
	[0x90, 0x90, 0xF0, 0x10, 0x10], # 4
	[0xF0, 0x80, 0xF0, 0x10, 0xF0], # 5
	[0xF0, 0x80, 0xF0, 0x90, 0xF0], # 6
	[0xF0, 0x10, 0x20, 0x40, 0x40], # 7
	[0xF0, 0x90, 0xF0, 0x90, 0xF0], # 8
	[0xF0, 0x90, 0xF0, 0x10, 0xF0], # 9
	[0xF0, 0x90, 0xF0, 0x90, 0x90], # A
	[0xE0, 0x90, 0xE0, 0x90, 0xE0], # B
	[0xF0, 0x80, 0x80, 0x80, 0xF0], # C
	[0xE0, 0x90, 0x90, 0x90, 0xE0], # D
	[0xF0, 0x80, 0xF0, 0x80, 0xF0], # E
	[0xF0, 0x80, 0xF0, 0x80, 0x80], # F
]

# ----------------------------------------------------------------------------------------------------------------------
# Globals
# ----------------------------------------------------------------------------------------------------------------------

display   = None  # Pygame display surface
skip_next = False # Skip next instruction?
all_done  = False # Whether or not PC is past last instruction
jumped    = False # Whether or not the last instruction used i_call() or i_jp()

# Memory
#     0 - 511 - Originally hold the interpreter, will only store sprites here
#     512     - Start of most Chip-8 programs
#     1536    - Start of ETI 660 Chip-8 programs
# Registers
#     Each register is 8-bit
#     Register I is 16-bit (usually holds mem addresses, which are 12-bit, right-aligned)
#     V[15] or V[F] is a flag used by instructions
# Sprites
#     Group of up to 15 bytes, or up to 8x15

# Hardware
RAM    = bytearray(4096)					# RAM, 4 KiB, indexed by bytes
STACK  = [bytearray(2) for _ in range(16)]	# Stack
V      = bytearray(16)       				# General-purpose registers, 8-bit
I      = bytearray(2)        				# Register, 16-bit
PC     = bytearray(2)        				# Program counter, 16-bit
SP     = bytearray(1)        				# Stack pointer, 8-bit
DT     = bytearray(1)        				# Delay timer, 8-bit
ST     = bytearray(1)        				# Sound timer, 8-bit
DISP   = [[False] * SCREEN_HEIGHT for _ in range(SCREEN_WIDTH)] # 64x32 monochrome display

# Fill start of memory with sprites
idx = 0
for sprite in SPRITES:
	for byte in sprite:
		RAM[idx] = byte
		idx += 1

# ----------------------------------------------------------------------------------------------------------------------
# Display Drawing
# ----------------------------------------------------------------------------------------------------------------------

# Draws a pixel at the given location in DISP
# Pixels will wrap around to opposite end of screen if out of bounds
# Will NOT update Pygame display
# Returns whether or not the pixel was overwritten
def draw_pixel(x: int, y: int):
	global display, DISP

	# Wrap coordinates onto visible screen
	xw = x % SCREEN_WIDTH
	yw = y % SCREEN_HEIGHT

	collision = DISP[xw][yw]
	DISP[xw][yw] = not collision
	
	return collision
	
# Draws a byte at the given location in DISP from left to right
# Bits are xor'd onto screen
# Bytes will wrap around to opposite end of screen if a bit is out of bounds
# Will NOT update Pygame display
# Returns whether or not a pixel was overwritten
def draw_byte(byte: int, x: int, y: int):
	collision = False
	
	bits = str(bin(byte))[2:]
	start = 8 - len(bits)
	
	for i in range(0, len(bits)):
		if bits[i] == '1':
			ret = draw_pixel(x + start + i, y)
			if ret: collision = True
		
	return collision
	
# Draws the display to the GUI according to DISP
def update_display():
	pygame.draw.rect(display, OFF_COLOR, (0, 0, SCALE*SCREEN_WIDTH, SCALE*SCREEN_HEIGHT))
	for x in range(len(DISP)):
		for y in range(len(DISP[x])):
			if DISP[x][y]: pygame.draw.rect(display, ON_COLOR, (x*SCALE, y*SCALE, SCALE, SCALE))
	pygame.display.update()

# ----------------------------------------------------------------------------------------------------------------------
# Instructions
# ----------------------------------------------------------------------------------------------------------------------

# Graphics -------------------------------------------------------------------------------------------------------------

# Clear the display
def i_cls():
	global DISP
	
	DISP = [[False] * SCREEN_HEIGHT for _ in range(SCREEN_WIDTH)]
	update_display()
	
# Display n-byte sprite starting at memory location I at (V[x], V[y]). V[F] = collision 
def i_drw(x: int, y: int, n: int):
	V[15] = 0
	
	# Draw the sprite
	for i in range(0, n):
		collision = draw_byte(RAM[btoi(I)+i], x, y+i)
		if collision: V[15] = 1
		update_display()
	
# Code Navigation ------------------------------------------------------------------------------------------------------
	
# Return from a subroutine
def i_ret():
	if SP[0] != 15: SP[0] -= 1
	copy_bytes(PC, STACK[btoi(SP)])
	if SP[0] == 15: SP[0] -= 1
	
# Jump to address with offset
def i_jp(offset: int, addr: int):
	global jumped

	copy_bytes(PC, itob(addr + offset, 2))
	jumped = True
	
# Call subroutine at address
def i_call(addr: int):
	global PC, jumped
	
	copy_bytes(STACK[SP[0]], PC)
	if SP[0] != 15: SP[0] += 1
	PC = itob(addr, 2)
	jumped = True
	
# Skip next instruction if Vx == byte
def i_se(x: int, byte: int):
	global PC, all_done
	
	pc_int = btoi(PC)
	if V[x] == byte:
		if pc_int == 0xFFFF: all_done = True
		else: PC = itob(pc_int + 2, 2)
		
# Skip next instruction if Vx != byte
def i_sne(x: int, byte: int):
	global PC, all_done
	
	pc_int = btoi(PC)
	if V[x] != byte:
		if pc_int == 0xFFFF: all_done = True
		else: PC = itob(pc_int + 2, 2)
		
# Skip next instruction if key with value V[x] is pressed
def i_skp(keyval: int):
	global PC, KEY
	
	try:
		if pygame.key.get_pressed()[KEY[keyval]]:
			pc_int = btoi(PC)
			if pc_int == 0xFFFF: all_done = True
			else: PC = itob(pc_int + 2, 2)
	except ValueError:
		print("Error in skp: Attempt to get value of key {}".format(hex(keyval)))
		sys.exit()
	
# Skip next instruction if key with given value is NOT pressed
def i_sknp(keyval: int):
	global PC, KEY
	
	try:
		if not pygame.key.get_pressed()[KEY[keyval]]:
			pc_int = btoi(PC)
			if pc_int == 0xFFFF: all_done = True
			else: PC = itob(pc_int + 2, 2)
	except ValueError:
		print("Error in sknp: Attempt to get value of key {}".format(hex(keyval)))
		sys.exit()

# Operations -----------------------------------------------------------------------------------------------------------

# Loads data into registers depending on inputs (several variants are included here,
# the documentation is fuzzy)
def i_ld(dest, src):
	global I
	
	# Fx07
	# Mode: V[dest] = Key (wait for one to be pressed)
	if src == WAITKEY:
		pygame.event.clear()
		while True:
			break_while = False
			event = pygame.event.wait()
			if event.type == pygame.QUIT:
				pygame.quit()
				sys.exit()
			elif event.type == KEYDOWN:
				for i in range(len(KEY)):
					if event.key == KEY[i]:
						V[dest] = i
						break_while = True
						break
			if break_while: break

	# Fx29
	# Mode: I = Location of sprite for digit V[x]
	elif dest == SPRITE:
		I = itob(src * 5, 2)
		
	# Fx33
	# Mode: I, I+1, I+2 = BCD representation of V[x]
	elif dest == BCD:
		RAM[btoi(I)  ] = src // 100
		RAM[btoi(I)+1] = (src % 100) // 10
		RAM[btoi(I)+2] = src % 10
		
	# Fx55
	# Mode: Store registers V[0] ... V[x] in Memory starting at I
	elif dest == SAVEREG:
		for i in range(0, src+1):
			RAM[btoi(I)+i] = V[i]
		
	# Fx65
	# Mode: Read registers V[0] ... V[x] from memory starting at I
	elif src == LOADREG:
		for i in range(0, dest+1):
			V[i] = RAM[btoi(I)+i]

	# Mode: Store value into register
	else:	
		# V[dest] = src. If dest is a bytearray, will use that rather than V[dest]
		if   isinstance(dest, bytearray):
			if   isinstance(src, int):       copy_bytes(dest, itob(src, len(dest)))
			elif isinstance(src, bytearray): copy_bytes(dest, src)
		elif isinstance(dest, int):
			if   isinstance(src, int):       V[dest] = src
			elif isinstance(src, bytearray): V[dest] = btoi(src)
		else:
			print("Error - Unexpected argument type to i_ld")
			sys.exit()

# Vx += byte. VF = carry. If x is a bytearray, will use that rather than Vx
def i_add(x, byte: int):
	val = 0
	carry = False
	
	if x is I:
		val = btoi(x) + byte
		# Too big for 16-bit register?
		carry = val > 65535
		val = itob(val & 0xFFFF, 2)
		copy_bytes(I, val)
	# x = index of V?
	elif isinstance(x, int):
		val = V[x] + byte
		# Too big for 8-bit register?
		carry = val > 255
		val &= 0xFF
		V[x] = val
	else:
		print("Error - Unexpected argument type to i_add")
		sys.exit()
	# Update V[F]
	if carry: V[15] = 1
	else    : V[15] = 0
	
# Vx -= Vy. VF = NOT borrow
def i_sub(x: int, y: int):
	borrow = V[x] < V[y] # <= ???
	V[15] = int(not borrow)
	V[x] = (V[x] - V[y]) & 0xFF
	
# Vx = Vy - Vx. VF = NOT borrow
def i_subn(x: int, y: int):
	borrow = V[y] < V[x]
	V[15] = int(not borrow)
	V[x] = (V[y] - V[x]) & 0xFF

def i_and(x: int, y: int): V[x] &= y
def i_or (x: int, y: int): V[x] |= y
def i_xor(x: int, y: int): V[x] ^= y

# Vx *= 2. VF = 1 if its previous MSB is 1
# y is unused
def i_shl(x: int, y: int):
	msb = (V[x] & 0b10000000) >> 7
	if msb == 0b1: V[15] = 1
	else         : V[15] = 0
	V[x] = (V[x] << 1) & 0xFF
	
# Vx /= 2. VF = 1 if its previous LSB is 1
# y is unused
def i_shr(x: int, y: int):
	lsb = V[x] & 0b00000001
	if lsb == 0b1: V[15] = 1
	else         : V[15] = 0
	V[x] >>= 1
	
# Vx = (random byte) & byte
def i_rnd(x, byte):
	V[x] = randint(0x0, 0xF) & byte

# ----------------------------------------------------------------------------------------------------------------------
# Instruction Parser
# ----------------------------------------------------------------------------------------------------------------------

# Each instruction is 2 bytes
def handle_instruction(instr: bytearray):
	global all_done
	
	# Hex symbols (nibbles/4 bits each)
	n1:   int = (instr[0] & 0xF0) >> 4
	n2:   int = (instr[0] & 0x0F)
	n3:   int = (instr[1] & 0xF0) >> 4
	n4:   int = (instr[1] & 0x0F)
	# Groups of nibbles
	n34:  int = instr[1]
	n234: int = (n2 << 8) + instr[1]

	if   n1==0x0 and n2==0x0 and n3==0x0 and n4==0x0 : all_done = True
	elif n1==0x0 and n2==0x0 and n3==0xE and n4==0x0 : i_cls  (                )
	elif n1==0x0 and n2==0x0 and n3==0xE and n4==0xE : i_ret  (                )
	elif n1==0x1                                     : i_jp   (0, n234         )
	elif n1==0x2                                     : i_call (n234            )
	elif n1==0x3                                     : i_se   (n2, n34         )
	elif n1==0x4                                     : i_sne  (n2, n34         )
	elif n1==0x5                                     : i_se   (n2, V[n3]       )
	elif n1==0x6                                     : i_ld   (n2, n34         )
	elif n1==0x7                                     : i_add  (n2, n34         )
	elif n1==0x8                         and n4==0x0 : i_ld   (n2, V[n3]       )
	elif n1==0x8                         and n4==0x1 : i_or   (n2, V[n3]       )
	elif n1==0x8                         and n4==0x2 : i_and  (n2, V[n3]       )
	elif n1==0x8                         and n4==0x3 : i_xor  (n2, V[n3]       )
	elif n1==0x8                         and n4==0x4 : i_add  (n2, V[n3]       )
	elif n1==0x8                         and n4==0x5 : i_sub  (n2, n3          )
	elif n1==0x8                         and n4==0x6 : i_shr  (n2, V[n3]       )
	elif n1==0x8                         and n4==0x7 : i_subn (n2, n3          )
	elif n1==0x8                         and n4==0xE : i_shl  (n2, V[n3]       )
	elif n1==0x9                         and n4==0x0 : i_sne  (n2, V[n3]       )
	elif n1==0xA                                     : i_ld   (I, n234         )
	elif n1==0xB                                     : i_jp   (V[0],  n234     )
	elif n1==0xC                                     : i_rnd  (n2, n34         )
	elif n1==0xD                                     : i_drw  (V[n2], V[n3], n4)
	elif n1==0xE             and n3==0x9 and n4==0xE : i_skp  (V[n2]           )
	elif n1==0xE             and n3==0xA and n4==0x1 : i_sknp (V[n2]           )
	elif n1==0xF             and n3==0x0 and n4==0x7 : i_ld   (n2, DT          )
	elif n1==0xF             and n3==0x0 and n4==0xA : i_ld   (n2, WAITKEY     )
	elif n1==0xF             and n3==0x1 and n4==0x5 : i_ld   (DT, V[n2]       )
	elif n1==0xF             and n3==0x1 and n4==0x8 : i_ld   (ST, V[n2]       )
	elif n1==0xF             and n3==0x1 and n4==0xE : i_add  (I, V[n2]        )
	elif n1==0xF             and n3==0x2 and n4==0x9 : i_ld   (SPRITE, V[n2]   )
	elif n1==0xF             and n3==0x3 and n4==0x3 : i_ld   (BCD, V[n2]      )
	elif n1==0xF             and n3==0x5 and n4==0x5 : i_ld   (SAVEREG, n2     )
	elif n1==0xF             and n3==0x6 and n4==0x5 : i_ld   (n2, LOADREG     )
	else: print("Unrecognized instruction {}".format(instr))
	
# Starting point of the emulator
def run_program():
	global all_done, PC, display, jumped, DT, ST
	
	# Gather source code
	read_file()

	# Start GUI
	pygame.init()
	romname = ROM.split('\\')
	romname = romname[len(romname)-1]
	pygame.display.set_caption("{} - Chip8 Emulator".format(romname))
	display = pygame.display.set_mode((64 * SCALE, 32 * SCALE))
	display.fill(OFF_COLOR)
	pygame.display.update()
	sound = None
	
	# Clock
	dt_clock = Clock()
	st_clock = Clock()
	dt_started = False
	st_started = False
	dt_elapsed = 0
	st_elapsed = 0
	
	# PC starts at byte 512
	PC = itob(512, 2)
	
	log("\n=======\nRUNNING\n=======\n")
	
	while not all_done:
		# Listen for pygame events (to avoid freezing + allow exiting)
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				pygame.quit()
				sys.exit()
		
		# Get instruction
		pc_int = btoi(PC)
		instr = bytearray([RAM[pc_int], RAM[pc_int+1]])
		log("{}:	{}".format(hex(btoi(PC)), hex(btoi(instr))))
		
		# Handle instruction
		handle_instruction(instr)
		
		# Check PC
		pc_int = btoi(PC)
		if pc_int == 0xFFFF - 1: all_done = True
		else:
			if not jumped: PC = itob(pc_int + 2, 2)
			else         : jumped = False
		
		#sleep(0.0000000000001)
		
		# Update timers + play sound if needed
		if DT[0] > 0:
			if not dt_started:
				dt_started = True
				dt_elapsed = 0
				dt_clock.tick()
			else:
				dt_elapsed += dt_clock.tick()
				if dt_elapsed / 1000 > 1/SPEED:
					DT[0] -= 1
					dt_elapsed = 0
					if DT[0] == 0: dt_started = False
		if ST[0] > 0:
			if sound == None or not sound.is_playing():
				sound = play_sound(SOUND_FREQUENCY, 1)
			
			if not st_started:
				st_started = True
				st_elapsed = 0
				st_clock.tick()
			else:
				st_elapsed += st_clock.tick()
				if st_elapsed / 1000 > 1/SPEED:
					ST[0] -= 1
					st_elapsed = 0
					if ST[0] == 0:
						st_started = False
						sound.stop()
	
# Moves source code of ROM into RAM
def read_file():
	# Get bytes
	file = open(ROM, "rb")
	source = list(file.read())
	
	log("\n======\nSOURCE\n======\n")
	i = 0
	while True:
		# Note: Some programs do NOT have a number of bytes that's a multiple of 2. Why?
		if i >= len(source) - 2: break
		log("{}: {}".format(hex(i+512), hex(btoi(bytearray([source[i], source[i+1]])))))
		i += 2
	
	file.close()
	for i, byte in enumerate(source):
		RAM[512 + i] = byte
	
# ----------------------------------------------------------------------------------------------------------------------
# Misc Functions
# ----------------------------------------------------------------------------------------------------------------------
	
# Convert bytearray to integer
def btoi(bytes): return int.from_bytes(bytes, byteorder="big", signed=False)

# Convert integer to bytearray(2)
def itob(intgr, length=2): return bytearray(intgr.to_bytes(length=length, byteorder="big", signed=False))

# Copies a byte array into another
def copy_bytes(dest, src):
	for i in range(0, len(src)): dest[i] = src[i]
	
# Prints message if debug mode enabled
def log(msg):
	if DEBUG: print(msg)
	
# Plays a sound (frequency in Hz, duration in Seconds)
def play_sound(freq, duration):
	fs = 44100
	t = np.linspace(0, duration, duration * fs, False)
	note = np.sin(freq*t*2*np.pi)
	audio = (note * (2**15 - 1) / np.max(np.abs(note))).astype(np.int16)
	sound = sa.play_buffer(audio, 1, 2, fs)
	return sound
	
# ----------------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------------
	
if __name__ == "__main__":
	if len(sys.argv) == 2: ROM = sys.argv[1]
	run_program()
	
# TODO
# 	Smooth graphic transitions
# 	Error checking
# 	Extra CHIP8 implementation support (resolutions, ...)
# 	Seperate files