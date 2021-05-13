# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

from uasyncio import sleep_ms
from common import dis, system, settings
from display import Display, FontSmall
from settings import Settings
from ux import KeyInputHandler

import utime
import random

# Game State Machine
READY_TO_PLAY = 1
THE_GAMES_AFOOT = 2
GAME_OVER = 3
TRYING_TO_QUIT = 4

SLITHER_RIGHT = 1
SLITHER_LEFT = 2
SLITHER_UP = 3
SLITHER_DOWN = 4

BLOCK_SIZE = 10

MIN_X = 0
MIN_Y = 30
MAX_X = 230
MAX_Y = 240

class Snack:
    def __init__(self, dis):
        self.dis = dis
        self.x = random.randrange(MIN_X, MAX_X, BLOCK_SIZE)
        self.y = random.randrange(MIN_Y, MAX_Y, BLOCK_SIZE)
        self.size = BLOCK_SIZE

    def newPosition(self):
        self.x = random.randrange(MIN_X, MAX_X - BLOCK_SIZE, BLOCK_SIZE)
        self.y = random.randrange(MIN_Y, MAX_Y - BLOCK_SIZE, BLOCK_SIZE)

    def draw(self):
        # self.dis.draw_rect(self.x, self.y, self.size, self.size, 5)
        self.dis.icon(self.x, self.y, 'fruit') 

class Snake:

    def __init__(self, dis, length):
        self.dis = dis
        self.length = length
        self.x=[]
        self.y=[]
        self.size = BLOCK_SIZE
        self.step = BLOCK_SIZE
        self.direction = SLITHER_RIGHT
        
        # Set starting position in center screen
        for i in range(0,self.length):
            self.x.append((MAX_X + MIN_X) // 2 + BLOCK_SIZE // 2)
            self.y.append((MAX_Y + MIN_Y) // 2 + BLOCK_SIZE // 2)
    
    def update(self):
        # Advance position of tail segments
        for i in range(self.length - 1,0,-1):
            self.x[i] = self.x[i-1]
            self.y[i] = self.y[i-1]

        # update head position
        if self.direction == SLITHER_RIGHT:
            self.x[0] = self.x[0] + self.step
        elif self.direction == SLITHER_LEFT:
            self.x[0] = self.x[0] - self.step
        elif self.direction == SLITHER_UP:
            self.y[0] = self.y[0] - self.step
        elif self.direction == SLITHER_DOWN:
            self.y[0] = self.y[0] + self.step


    def addSegment(self):
        self.x.append(self.x[self.length - 1])
        self.y.append(self.y[self.length - 1])
        self.length += 1
        

    def move(self, direction):
        self.direction = direction

    def draw(self): 
        for i in range(0, self.length):
            self.dis.draw_rect(self.x[i], self.y[i], self.size, self.size, 5)

    def isCollision(self,x,y):
        for i in range(0, self.length):
            if (x == self.x[i] and y == self.y[i]):
                return True
        return False


class Game: 

    def __init__(self):
        self.dis = dis
        self.font = FontSmall
        self.running = True
        self.pending_direction = SLITHER_RIGHT
        self.prev_time = 0
        self.state = READY_TO_PLAY
        self.score = 0
        self.speed = 100;
        self.highscore = 0
        self.snake = Snake(self.dis, 3)
        self.snack = Snack(self.dis)
        self.input = KeyInputHandler(down='udplrxy', up='xy')

        # ensure initial snack spawn isn't on snake
        while (self.snake.isCollision(self.snack.x, self.snack.y)):
            self.snack.newPosition()

    def isCollision(self,x1,y1,x2,y2):
        if x1 == x2 and y1 == y2:
            return True
        return False

    def move(self, direction):
        self.pending_direction = direction

    def render(self):
        
        self.dis.clear()
        self.dis.draw_header('Score: {}'.format(self.score), left_text = str(self.highscore))

        # draw arena bounding box
        self.dis.draw_rect(MIN_X, MIN_Y, MAX_X, MAX_Y, 2)


        # rendering of snake, snacks, etc
        if self.state == READY_TO_PLAY:
            self.snake.draw()

        if self.state == THE_GAMES_AFOOT:
            self.snake.draw()
            self.snack.draw()
        
        # rendering of game over screen
        if self.state == GAME_OVER:
            POPUP_WIDTH = 180
            POPUP_HEIGHT = 100
            POPUP_X = Display.HALF_WIDTH - (POPUP_WIDTH // 2)
            POPUP_Y = Display.HALF_HEIGHT - (POPUP_HEIGHT // 2)
            self.dis.draw_rect(POPUP_X, POPUP_Y, POPUP_WIDTH, POPUP_HEIGHT, 4)
            self.dis.text(None, Display.HALF_HEIGHT - 3 * self.font.leading // 4 - 9, 'GAME OVER!')
            self.dis.text(None, Display.HALF_HEIGHT                              - 9, 'Score: ' + str(self.score))
            self.dis.text(None, Display.HALF_HEIGHT + 3 * self.font.leading // 4 - 9, 'Highscore: ' + str(self.highscore))
       
        # rendering quit confirmation screen
        if self.state == TRYING_TO_QUIT:
            POPUP_WIDTH = 180
            POPUP_HEIGHT = 200
            POPUP_X = Display.HALF_WIDTH - (POPUP_WIDTH // 2)
            POPUP_Y = Display.HALF_HEIGHT - (POPUP_HEIGHT // 2)
            self.dis.draw_rect(POPUP_X, POPUP_Y, POPUP_WIDTH, POPUP_HEIGHT, 4)
            self.dis.text(None, Display.HALF_HEIGHT - 3 * self.font.leading // 4 - 9, 'Are you sure you')
            self.dis.text(None, Display.HALF_HEIGHT                              - 9, 'want to quit? ')
        

        # rendering of footer
        if self.state == READY_TO_PLAY or self.state == GAME_OVER:
            right_btn = 'START'
            left_btn = 'BACK'
        elif self.state == THE_GAMES_AFOOT:
            right_btn = ''
            left_btn = "BACK"
        elif self.state == TRYING_TO_QUIT:
            right_btn = 'YES'
            left_btn = 'NO'

        self.dis.draw_footer(left_btn, right_btn, self.input.is_pressed('x'), self.input.is_pressed('y'))
        self.dis.show()

    # tracking game logic and do collision checking.
    def update(self, now):
        if (now - self.prev_time > self.speed):
            self.prev_time = now
            
            if self.state == THE_GAMES_AFOOT:
                self.snake.direction = self.pending_direction
                self.snake.update()
                
                # snake is updated but not drawn yet, check for collisions....
                
                # if snek leaves game arena, wrap to other side.
                if (self.snake.x[0] > MIN_X + MAX_X - BLOCK_SIZE):
                    self.snake.x[0] = MIN_X
                elif (self.snake.x[0] < MIN_X):
                    self.snake.x[0] = MIN_X + MAX_X - BLOCK_SIZE
                elif (self.snake.y[0] > MIN_Y + MAX_Y - BLOCK_SIZE):
                    self.snake.y[0] = MIN_Y
                elif (self.snake.y[0] < MIN_Y):
                    self.snake.y[0] = MIN_Y + MAX_Y - BLOCK_SIZE

                # if snek eat snac
                if (self.isCollision(self.snake.x[0], self.snake.y[0], self.snack.x, self.snack.y)):
                    self.snake.addSegment()
                    self.snack.newPosition()
                    while (self.snake.isCollision(self.snack.x, self.snack.y)):
                        self.snack.newPosition()
                    self.score += 1
                    self.speed = 0.98 * self.speed

                # if snek eat snek
                for i in range(1, self.snake.length):
                    if self.isCollision(self.snake.x[0], self.snake.y[0], self.snake.x[i], self.snake.y[i]):
                        self.state = GAME_OVER

                if self.score > self.highscore:
                    self.highscore = self.score
            
    def start(self):
        self.state = THE_GAMES_AFOOT
        self.score = 0
        self.snake.length = 3
        for i in range(0,self.snake.length):
            self.snake.x[i] = (MAX_X + MIN_X) // 2 + BLOCK_SIZE // 2
            self.snake.y[i] = (MAX_Y + MIN_Y) // 2 + BLOCK_SIZE // 2
        self.prev_time = utime.ticks_ms()


async def snake_game():

    # Game functions and settings
    game = Game()
    game.highscore = settings.get('snake_highscore', 0)

    input = KeyInputHandler(down='udplrxy', up='xy')

    while game.running:
        event = await input.get_event()

        if event != None:
            # Handle key event and update game state
            key, event_type = event

            if event_type == 'down':
                if key == 'l':
                    game.move(SLITHER_LEFT)
                elif key == 'r':
                    game.move(SLITHER_RIGHT)
                elif key == 'u':
                    game.move(SLITHER_UP)
                elif key == 'd':
                    game.move(SLITHER_DOWN)

            elif event_type == 'up':
                if key == 'x':
                    if game.state == THE_GAMES_AFOOT:
                        game.state = TRYING_TO_QUIT
                    elif game.state == TRYING_TO_QUIT:
                        game.state = THE_GAMES_AFOOT
                    elif game.state == READY_TO_PLAY or game.state == GAME_OVER:
                        game.running = False

                elif key == 'y':
                    if game.state == READY_TO_PLAY or game.state == GAME_OVER:
                        game.start()
                    elif game.state == TRYING_TO_QUIT:
                        game.running = False

        system.turbo(True)
        game.update(utime.ticks_ms())
        game.render()
        system.turbo(False)
        await sleep_ms(1)

    settings.set('snake_highscore', game.highscore)
    return None
