# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

from uasyncio import sleep_ms
from common import dis, noise, settings, system
from display import Display, FontSmall
from ux import KeyInputHandler
import utime


READY_TO_PLAY = 1
GAME_IN_PROGRESS = 2
GAME_OVER = 3
TRYING_TO_QUIT = 4
PAUSED = 5

BLOCK_SIZE = 12

MIN_X = 0
MAX_Y = 22 * BLOCK_SIZE - 4

BLOCK_FALLING_X = 5
BLOCK_FALLING_Y = 20
BLOCK_NEXT_X = 14
BLOCK_NEXT_Y = 13

SPAWN_AREA = 6

SPEED_FAST = 1
SPEED_SLOW = 500

SHAPE_S = 0
SHAPE_T = 1
SHAPE_L = 2
SHAPE_Lb = 3
SHAPE_Z = 4
SHAPE_Zb = 5
SHAPE_I = 6

class Block:
    """
    Block grid
    ---------------------
    | 0  | 1  | 2  | 3  |
    ---------------------
    | 4  | 5  | 6  | 7  |
    ---------------------
    | 8  | 9  | 10 | 11 |
    ---------------------
    | 12 | 13 | 14 | 15 | 
    ---------------------
    """
    
    # block = block_map[type][rotation]
    block_map = [
            [[5,6,9,10]],                                   # Square
            [[4,1,5,9], [4,5,1,6],[1,5,6,9],[4,5,6,9]],     # T
            [[1,5,9,10],[8,4,5,6],[0,1,5,9],[4,5,6,2]],     # L
            [[8,9,5,1], [0,4,5,6],[1,5,9,2],[4,5,6,10]],    # L - reversed
            [[0,1,5,6], [9,5,6,2]],                         # Z
            [[4,5,1,2], [1,5,6,10]],                        # Z - reversed
            [[1,5,9,13],[4,5,6,7]],                         # I
    ]

    def __init__(self, dis, x, y):
        self.dis = dis
        self.x = x
        self.y = y
        (n1, _) = noise.read()        
        self.type = n1 % len(self.block_map)

        # self.type = 0 # debug to force squares
        # self.rot = random.randint(0, len(self.block_map[self.type]) - 1)
        self.rot = 0 # able to get the next box smaller ('I' doesn't stick out 4 units on x)

    def moveBlock(self, direction):
        if direction == 'l':
            self.x -= 1
        elif direction == 'r':
            self.x += 1
        elif direction == 'd':
            self.y -= 1

    def rotateBlock(self):
        self.rot = (self.rot + 1) % len(self.block_map[self.type])

    def draw(self, offset_x, offset_y):
        for i in range(0, len(self.block_map[self.type][self.rot])):
            self.dis.icon(MIN_X + BLOCK_SIZE * (self.x + (self.block_map[self.type][self.rot][i] % 4)) + offset_x,
                MAX_Y - BLOCK_SIZE * (self.y + ((self.block_map[self.type][self.rot][i] // 4) % 4)) - offset_y, 
                'tetris_pattern_' + str(self.type))

class Map:

    def __init__(self):
        self.dis = dis
        self.width = 12
        self.height = 20 + SPAWN_AREA # screen hight: 20, spawn hight: 4, anything more is extra
        self.grid = [[-1 for col in range(self.width)] for row in range(self.height)] # -1 for empty, 0-6 for color, set during game.
        self.score = 0
        self.highscore = 0
    
    def deleteFilledRows(self):
        row = 0
        while row < self.height - SPAWN_AREA:
            # check for rows with filled columns
            for col in range(0, self.width):
                if self.grid[row][col] == -1: # if at any point a row has an empty block, skip to the next row 
                    break     
                if col == (self.width - 1): # if entire column is filled shift all rows above it down.
                    # print("deleting row")
                    for new_row in range(row, self.height - SPAWN_AREA):
                        for col in range(0, self.width):
                            self.grid[new_row][col] = self.grid[new_row + 1][col]
                    self.score += 1
                    if self.score > self.highscore:
                        self.highscore = self.score
                    row -= 1 # check same row again as the map has shifted
            row += 1

    def isGameOver(self):
        for col in range(0, self.width):
            for row in range(20, self.height): # check for blocks in spawn area
                if self.grid[row][col] >= 0:
                    return True
        return False


    def draw(self):
        self.dis.draw_rect(MIN_X, MAX_Y - (self.height-1)*BLOCK_SIZE, self.width * BLOCK_SIZE, self.height * BLOCK_SIZE, 0)
        for col in range(0, self.width):
            for row in range(0, self.height):
                if self.grid[row][col] >= 0:  
                    self.dis.icon(MIN_X + col * BLOCK_SIZE, MAX_Y - row * BLOCK_SIZE, 'tetris_pattern_' + str(self.grid[row][col])) 
        
class Game:

    def __init__(self, KeyInput):
        self.dis = dis
        self.font = FontSmall
        self.running = True
        self.state = READY_TO_PLAY
        self.prev_time = 0
        self.speed = SPEED_SLOW
        self.input = KeyInput
        self.map = Map()
        self.falling_block = Block(self.dis, BLOCK_FALLING_X, BLOCK_FALLING_Y)
        self.next_block = Block(self.dis, BLOCK_NEXT_X, BLOCK_NEXT_Y)
        self.temp_block = Block(self.dis, 0, 0)
        self.left_btn = ''
        self.right_btn = ''
        self.isLRkeyPressed = False

    def blockInSpawn(self):
        for i in range(0, 4):
            if ((self.falling_block.y + ((self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] // 4) % 4)) >= self.map.height): # or ((self.falling_block.y + ((self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] // 4) % 4)) < 0):
                # print("blockInSpawn() = True")
                return True
        # print("blockInSpawn() = True")
        return False


    def isCollisionWall(self, direction):
        self.temp_block.x = self.falling_block.x
        self.temp_block.y = self.falling_block.y
        self.temp_block.type = self.falling_block.type
        self.temp_block.rot = self.falling_block.rot

        if direction == 'o':
            self.temp_block.rotateBlock()
        else:
            self.temp_block.moveBlock(direction)

        for i in range(4):
            if (direction == 'r' or direction == 'o') and ((self.temp_block.x + (self.temp_block.block_map[self.temp_block.type][self.temp_block.rot][i] % 4)) >= self.map.width):
                return 'r'    
            elif (direction == 'l' or direction == 'o') and ((self.temp_block.x + (self.temp_block.block_map[self.temp_block.type][self.temp_block.rot][i] % 4)) < 0):
                return 'l'
            elif (direction == 'd' or direction == 'o') and ((self.temp_block.y + ((self.temp_block.block_map[self.temp_block.type][self.temp_block.rot][i] // 4) % 4)) <  0):
                return 'd'

        return False

    # direction must be either 'o', 'r', 'l', 'd'
    def isCollisionMap(self, direction):
        self.temp_block.x = self.falling_block.x
        self.temp_block.y = self.falling_block.y
        self.temp_block.type = self.falling_block.type
        self.temp_block.rot = self.falling_block.rot

        if direction == 'o':
            self.temp_block.rotateBlock()
        else:
            self.temp_block.moveBlock(direction)

        for i in range(4):
            # is part of block colliding with block embedded in map.grid[row][col]
            if self.map.grid[(self.temp_block.y + ((self.temp_block.block_map[self.temp_block.type][self.temp_block.rot][i] // 4) % 4))][(self.temp_block.x + (self.temp_block.block_map[self.temp_block.type][self.temp_block.rot][i] % 4))] >= 0:
                return True

        return False

    def drawBackground(self):
        self.dis.draw_rect(0, Display.HEADER_HEIGHT, Display.WIDTH, Display.HEIGHT - Display.FOOTER_HEIGHT, 0, fill_color=1),
        # self.dis.draw_rect(MIN_X + BLOCK_SIZE, MIN_Y, 12 * BLOCK_SIZE, 20 * BLOCK_SIZE, 2)
        self.dis.draw_rect(MIN_X + 26 * BLOCK_SIZE // 2 + 3, MAX_Y - 33 * BLOCK_SIZE // 2, 5 * BLOCK_SIZE, 5 * BLOCK_SIZE, 2)
        self.dis.text(MIN_X + 27 * BLOCK_SIZE // 2 + 3, MAX_Y - 37 * BLOCK_SIZE // 2, 'Next:', invert=1)

        self.dis.text(MIN_X + 27 * BLOCK_SIZE // 2 + 3, 150, 'Stack', invert=1)
        self.dis.text(MIN_X + 27 * BLOCK_SIZE // 2 + 6, 150 + self.font.leading, 'Sats!', invert=1)

    def embedBlockInMap(self):
        # print("embedBlockInMap()")
        # Block must be checked to be entirly within map bounds before embedding using isCollision
        for i in range(4):
            # print("checkrow[" + str(i) + "] = " + str(self.falling_block.y + ((self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] // 4) % 4)))
            # print("checkcol[" + str(i) + "] = " + str(self.falling_block.x + (self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] % 4)))
            self.map.grid[self.falling_block.y + ((self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] // 4) % 4)][self.falling_block.x + (self.falling_block.block_map[self.falling_block.type][self.falling_block.rot][i] % 4)] = self.falling_block.type
            
    def spawnBlock(self):
        self.falling_block = self.next_block
        self.falling_block.x = BLOCK_FALLING_X
        self.falling_block.y = BLOCK_FALLING_Y
        self.next_block = Block(self.dis, BLOCK_NEXT_X, BLOCK_NEXT_Y)

    def start(self):
        self.score = 0
        for col in range(self.map.width):
            for row in range(self.map.height):
                self.map.grid[row][col] = -1 # clear game map
        self.state = GAME_IN_PROGRESS
        
    def drawNextBlock(self):
        if self.next_block.type == SHAPE_S:
            self.next_block.draw(-3,0)
        elif self.next_block.type == SHAPE_T:
            self.next_block.draw(9,6)
        elif self.next_block.type == SHAPE_L:
            self.next_block.draw(0,6)
        elif self.next_block.type == SHAPE_Lb:
            self.next_block.draw(6,6)
        elif self.next_block.type == SHAPE_Z:
            self.next_block.draw(3,9)
        elif self.next_block.type == SHAPE_Zb:
            self.next_block.draw(3,9)
        elif self.next_block.type == SHAPE_I:
            self.next_block.draw(3,0)

    def render(self):
        self.dis.clear()
        self.drawBackground()
        self.map.draw()

        if self.state == READY_TO_PLAY:
            self.left_btn = 'BACK'
            self.right_btn = 'PLAY'
        
        elif self.state == GAME_IN_PROGRESS:
            self.left_btn = 'BACK'
            self.right_btn = 'PAUSE'
            self.falling_block.draw(0,0)
            self.drawNextBlock()

        elif self.state == PAUSED:
            self.left_btn = 'BACK'
            self.right_btn = 'RESUME'
            self.falling_block.draw(0,0)
            self.drawNextBlock()
            POPUP_WIDTH = 180
            POPUP_HEIGHT = 100
            POPUP_X = Display.HALF_WIDTH - (POPUP_WIDTH // 2)
            POPUP_Y = Display.HALF_HEIGHT - (POPUP_HEIGHT // 2)
            SCORE_Y = Display.HALF_HEIGHT - 12
            self.dis.draw_rect(POPUP_X, POPUP_Y, POPUP_WIDTH, POPUP_HEIGHT, 4)
            self.dis.text(None, SCORE_Y, 'Paused')

        elif self.state == GAME_OVER:
            self.left_btn = 'BACK'
            self.right_btn = 'PLAY'
            POPUP_WIDTH = 180
            POPUP_HEIGHT = 100
            POPUP_X = Display.HALF_WIDTH - (POPUP_WIDTH // 2)
            POPUP_Y = Display.HALF_HEIGHT - (POPUP_HEIGHT // 2)
            SCORE_Y = Display.HALF_HEIGHT - 12
            self.dis.draw_rect(POPUP_X, POPUP_Y, POPUP_WIDTH, POPUP_HEIGHT, 4)
            self.dis.text(None, SCORE_Y - self.font.leading, 'GAME OVER!')
            self.dis.text(None, SCORE_Y, 'Score: ' + str(self.map.score))
            self.dis.text(None, SCORE_Y + self.font.leading, 'High: ' + str(self.map.highscore))

        elif self.state == TRYING_TO_QUIT:
            self.left_btn = 'NO'
            self.right_btn = 'YES'
            POPUP_WIDTH = 180
            POPUP_HEIGHT = 100
            POPUP_X = Display.HALF_WIDTH - (POPUP_WIDTH // 2)
            POPUP_Y = Display.HALF_HEIGHT - (POPUP_HEIGHT // 2)
            TEXT_Y = POPUP_Y + POPUP_HEIGHT // 2 - self.font.leading
            self.dis.draw_rect(POPUP_X, POPUP_Y, POPUP_WIDTH, POPUP_HEIGHT, 4)
            self.dis.text(None, TEXT_Y, 'Are you sure you')
            self.dis.text(None, TEXT_Y + self.font.leading, 'want to quit? ')

        # draw header over blocks so they dont draw over it when 'out-of-bounds'
        self.dis.draw_header('Score: {}'.format(self.map.score), left_text = str(self.map.highscore))

        # Draw over the header's white bottom border
        self.dis.draw_rect(0, Display.HEADER_HEIGHT - 2, Display.WIDTH, 2, 0, fill_color=1),

        self.dis.draw_footer(self.left_btn, self.right_btn, self.input.is_pressed('x'), self.input.is_pressed('y'))
        self.dis.show()

    def update(self, now):
        if (now - self.prev_time > self.speed - (self.map.score * 5)):
            self.prev_time = now
            # print("isLRkeyPressed = " + str(self.isLRkeyPressed))
            if self.state == GAME_IN_PROGRESS:
                if (self.isCollisionWall('d') or self.isCollisionMap('d')):
                    self.embedBlockInMap()
                    if self.map.isGameOver():
                        self.state = GAME_OVER
                    else:
                        self.spawnBlock()
                        self.map.deleteFilledRows()
                else:
                    self.falling_block.moveBlock('d')
                    if self.input.is_pressed('r'):
                        if self.isCollisionWall('r') == False:
                            if self.isCollisionMap('r') == False:
                                self.falling_block.moveBlock('r')
                    elif self.input.is_pressed('l'):
                        if self.isCollisionWall('l') == False:
                            if self.isCollisionMap('l') == False:
                                self.falling_block.moveBlock('l')

                    if (self.input.is_pressed('r')) or (self.input.is_pressed('l')):
                        self.isLRkeyPressed = True
                    else:
                        self.isLRkeyPressed = False


async def stacking_sats_game():
    
    input = KeyInputHandler(down='udplrxy', up='xy')

    game = Game(input)
    game.map.highscore = settings.get('sats_highscore', 0)

    while game.running:
        event = await input.get_event()

        if input.is_pressed('d'):
            game.speed = SPEED_FAST
        else:
            game.speed = SPEED_SLOW 

        if event != None:
            key, event_type = event

            if event_type == 'down':
                if key == 'l':
                    if game.isCollisionWall(key) == False:
                        if game.isCollisionMap(key) == False:
                            game.falling_block.moveBlock(key)
                elif key == 'r':
                    if game.isCollisionWall(key) == False:
                        if game.isCollisionMap(key) == False:
                            game.falling_block.moveBlock(key)
                elif key == 'u':
                    collision_wall = game.isCollisionWall('o')
                    if collision_wall == False:
                        if game.isCollisionMap('o') == False:
                            game.falling_block.rotateBlock()
                        else:
                            pass
                            # print("Collision with block in map when trying to rotate")
                    elif collision_wall == 'l':
                        # print("Left wall collision when trying to rotate")
                        if game.isCollisionMap('r') == False:
                            game.falling_block.moveBlock('r')
                            if game.isCollisionWall('o') == False:
                                if game.isCollisionMap('o') == False:
                                    game.falling_block.rotateBlock()

                    elif collision_wall == 'r':
                        # print("Right wall collision when trying to rotate")
                        if game.isCollisionMap('l') == False:
                            game.falling_block.moveBlock('l')
                            if game.isCollisionWall('o') == False:
                                if game.isCollisionMap('o') == False:
                                    game.falling_block.rotateBlock()
                            else: # corner case where a straight piece is flush with right wall and tries to rotate
                                if game.isCollisionMap('l') == False:
                                    game.falling_block.moveBlock('l')
                                    if game.isCollisionWall('o') == False:
                                        game.falling_block.rotateBlock()
                elif key == 'd':
                    pass
                elif key == 'x':
                    pass
                elif key == 'y':
                    pass

            elif event_type == 'up':
                if key == 'x':
                    # print("x-up")
                    if game.state == GAME_IN_PROGRESS:
                        game.state = TRYING_TO_QUIT
                    elif game.state == TRYING_TO_QUIT:
                        game.state = GAME_IN_PROGRESS
                    elif (game.state == READY_TO_PLAY) or (game.state == GAME_OVER):
                        game.running = False
                elif key == 'y':
                    # print("y-up")
                    if (game.state == READY_TO_PLAY) or (game.state == GAME_OVER):
                        game.start()
                    elif game.state == GAME_IN_PROGRESS:
                        game.state = PAUSED
                    elif game.state == PAUSED:
                        game.state = GAME_IN_PROGRESS
                    elif game.state == TRYING_TO_QUIT:
                        game.running = False

        system.turbo(True)
        game.update(utime.ticks_ms())
        game.render()
        system.turbo(False)
        await sleep_ms(10)

    settings.set('sats_highscore', game.map.highscore)
    return None
