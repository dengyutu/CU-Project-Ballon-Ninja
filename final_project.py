import numpy as np
import RPi.GPIO as GPIO
import pygame, os, math, time, random
from pygame.locals import *
import cv2
import numpy as np
import threading
from picamera.array import PiRGBArray
from picamera import PiCamera

use_piTFT = False #change to True if you want to use piTFT
X,Y = 3,2.4 #amplify width and height

if use_piTFT:
    X,Y = 1,1 
    os.putenv('SDL_VIDEODRIVER', 'fbcon')  # Display on piTFT
    os.putenv('SDL_FBDEV', '/dev/fb0')
    #os.putenv('SDL_FBDEV', '/dev/fb1')
    os.putenv('SDL_MOUSEDRV', 'TSLIB')  # Track mouse clicks on piTFT
    os.putenv('SDL_MOUSEDEV', '/dev/input/touchscreen')

GPIO.setmode(GPIO.BCM)
GPIO.setup(27,GPIO.IN,pull_up_down=GPIO.PUD_UP) #Quit program immediately
pygame.init()

width, height= 320, 240  # Define width and height
screen = pygame.display.set_mode((int(width*X),int(height*Y)))
pygame.display.set_caption("Balloon Popping Game")
WHITE = 255, 255, 255
BLACK = 0, 0, 0
RED = 255, 0, 0
YELLOW = 255, 255 , 0
GREEN = 0, 255, 0
BLUE = 0, 0, 255
amplification_factors = (4*X, 4*Y) 
camera_resolution = (80, 60)
blue_lower = np.array([100, 135, 60], np.uint8)
blue_upper = np.array([150, 255, 255], np.uint8)


#Load some images
background1 = pygame.transform.scale(pygame.image.load("BG1.png"), (int(width*X),int(height*Y)))
background2 = pygame.transform.scale(pygame.image.load("BG2.png"), (int(width*X),int(height*Y)))
background3 = pygame.transform.scale(pygame.image.load("BG3.png"), (int(width*X),int(height*Y)))
background4 = pygame.transform.scale(pygame.image.load("BG4.png"), (int(width*X),int(height*Y)))
balloons_info = {
    'red': {'image': pygame.transform.scale(pygame.image.load('red.png'), (int(80*X), int(80*Y))), 'score': -5},
    'blue': {'image': pygame.transform.scale(pygame.image.load('blue.png'), (int(80*X), int(80*Y))), 'score': 2},
    'green': {'image': pygame.transform.scale(pygame.image.load('green.png'), (int(60*X), int(60*Y))), 'score': 5},
    'yellow': {'image': pygame.transform.scale(pygame.image.load('yellow.png'), (int(40*X), int(40*Y))), 'score': 10}}
water_image = pygame.transform.scale(pygame.image.load('water.png').convert_alpha(), (int(60*X), int(60*Y)))
bomb_image = pygame.transform.scale(pygame.image.load('bomb.png').convert_alpha(), (int(80*X), int(80*Y)))

class Animation:
    def __init__(self, position, animation_type):
        self.position = position
        self.original_image =  water_image if animation_type == 'water' else bomb_image
        self.image = self.original_image.copy()
        self.opacity = 255
        self.surface = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)

    def draw(self, screen):
        if self.opacity > 0:
            self.surface.fill((255, 255, 255, self.opacity))
            self.image.blit(self.original_image, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(self.image, self.position)
        self.opacity -= 0.2

class Balloon:
    def __init__(self):
        self.x = random.randint(40*X, (width-40)*X)
        self.y = (height - 20)*Y
        self.rotation_angle = 0
        self.rotation_speed = random.randint(-5, 5)
        self.speed = random.randint(40*X,55*X)
        if use_piTFT: self.speed = random.randint(20,30)
        self.angle = random.uniform(math.pi / 3, math.pi / 2) 
        if width / 4 <= self.x < 3 * width / 4:
            if random.choice([True, False]):
                self.angle = math.pi - self.angle 
        elif self.x > 3 * width / 4:
            self.angle = math.pi - self.angle 
        self.color = random.choice(['red', 'blue', 'green', 'yellow'])
        self.image = balloons_info[self.color]['image']
        self.score = balloons_info[self.color]['score']
        self.rect = self.image.get_rect(center=(self.x, self.y))
        self.time = 0

    def draw(self):
        rotated_image = pygame.transform.rotate(self.image, self.rotation_angle)
        screen.blit(rotated_image, rotated_image.get_rect(center=self.rect.center))

    def move(self):
        self.time += 0.2
        gravity = 6*X
        if use_piTFT: gravity = 2
        self.rect.x = int(self.x + self.speed * math.cos(self.angle) * self.time)
        self.rect.y = int(self.y - (self.speed * math.sin(self.angle) * self.time - 0.5 * gravity * self.time ** 2))
        if self.rect.y > (height+50)*Y or self.rect.x < (-50)*X or self.rect.x > (width+50)*X:
            balloons.remove(self)
        self.rotation_angle += self.rotation_speed

class ColorTracker:
    def __init__(self):
        self.camera = PiCamera()
        self.camera.resolution = camera_resolution
        self.camera.framerate = 30
        self.raw_capture = PiRGBArray(self.camera, size=camera_resolution)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.color_center = (None, None)

    def start(self):
        threading.Thread(target=self.camera_stream).start()
        threading.Thread(target=self.process_stream).start()

    def camera_stream(self):
        for f in self.camera.capture_continuous(self.raw_capture, format="bgr", use_video_port=True):
            with self.lock:
                self.frame = f.array
                self.raw_capture.truncate(0)
            if not self.running:
                break

    def process_stream(self):
        while self.running:
            with self.lock:
                if self.frame is not None:
                    self.process_frame(self.frame)

    def process_frame(self, f):
        f_flipped = cv2.flip(f, -1)  # Flip the frame
        hsv = cv2.cvtColor(f_flipped, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, blue_lower, blue_upper)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
    
            # Amplify rectangle coordinates and size
            ax, ay, aw, ah = (int(x * amplification_factors[0]), int(y * amplification_factors[1]),
                              int(w * amplification_factors[0]), int(h * amplification_factors[1]))
            center_x, center_y = int(ax + aw/ 2), int(ay + ah/ 2)

            # Resize the frame for display
            f_resized = cv2.resize(f_flipped, (0, 0), fx=amplification_factors[0], fy=amplification_factors[1])
            cv2.rectangle(f_resized, (ax, ay), (ax + aw, ay + ah), (0, 255, 0), 2)
            cv2.circle(f_resized, (center_x, center_y), 5, (0, 0, 255), -1)
            #print("Amplified Center: (", center_x, ",", center_y, ")")
            self.color_center = (center_x, center_y)    
        else:
            f_resized = cv2.resize(f_flipped, (0, 0), fx=amplification_factors[0], fy=amplification_factors[1])
        if not use_piTFT:
            cv2.imshow("Frame", f_resized)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.running = False
            
    def get_center(self):
        return self.color_center

def GPIO27_cb(channel):
    global run
    print("Physical Quit Button Pressed")
    run = False

# show buttons on the screen window
def Buttons(buttons, fontsize, color):
    my_font = pygame.font.Font(None, fontsize)
    for my_text, text_pos in buttons.items():
        text_surface = my_font.render(my_text, True, color)
        rect = text_surface.get_rect(center=text_pos)
        screen.blit(text_surface, rect)

def Background(bg):
    if bg == 1:
        screen.blit(background1,(0,0))
    elif bg == 2:
        screen.blit(background2,(0,0))
    elif bg == 3:
        screen.blit(background3,(0,0))
    elif bg == 4:
        screen.blit(background4,(0,0))
        
def ButtonLV1():
    Background(bg)
    Buttons({"START": (160*X, 120*Y)}, int(50*X), BLACK)
    Buttons({"Quit":(290*X,225*Y)}, int(30*X), WHITE)
    Buttons({"<":(25*X,120*Y),">":(295*X,120*Y)}, int(60*X), YELLOW)
    
def ButtonLV2():
    global HS,CS,CD
    Background(bg)
    Buttons({"Difficulty Selection": (160*X, 30*Y)}, int(40*X), BLACK)
    Buttons({"EASY":(160*X,90*Y)}, int(40*X), GREEN)
    Buttons({"HARD":(160*X,150*Y)}, int(40*X), RED)
    Buttons({"Highest Score: "+str(HS): (55*X,230*Y)}, int(20*X), YELLOW)
    Buttons({"Back":(290*X,225*Y)}, int(30*X), WHITE)

def ButtonLV3(gametime):
    global HS,CS,CD
    Background(bg)
    if gametime < 2.5:
        Buttons({str(3 - int(gametime)): (160*X,120*Y)}, int(100*X), BLACK)
    elif 3 > gametime >2.5:
        Buttons({"GO!": (160*X,120*Y)}, int(100*X), BLACK)
    else:
        Buttons({"Time: "+str(CD+3-int(gametime))+"s":(280*X,20*Y)}, int(25*X), WHITE)
    Buttons({"Highest Score: "+str(HS): (65*X,10*Y)}, int(20*X), WHITE)
    Buttons({"Current Score: "+str(CS): (65*X,30*Y)}, int(20*X), WHITE)
    Buttons({"End":(295*X,225*Y)}, int(30*X), WHITE)

def ButtonLV4():
    global HS,CS,CD
    Background(bg)
    Buttons({"Congratulation !":(160*X,40*Y)}, int(55*X), BLACK)
    Buttons({"You got "+str(CS)+" Points":(160*X,80*Y)}, int(35*X), YELLOW)
    Buttons({"Play Again":(90*X,160*Y)}, int(25*X), GREEN)
    Buttons({"Another Difficulty":(230*X,160*Y)}, int(25*X), BLUE)
    Buttons({"Home":(285*X,225*Y)}, int(30*X), WHITE)

GPIO.add_event_detect(27,GPIO.FALLING,callback=GPIO27_cb,bouncetime=300)

global HS,CS,CD,CDS
HS = 0 #highest score
CD = 30 #countdown in second

run = True
level = 1  # Switch between level 1-4 menus
bg = 1 #switch between 4 backgrounds
hard = False #Difficulty selection

clock = pygame.time.Clock()
balloons = []
animations = []
slicing = False
slicing_path = []
tracker = ColorTracker()
tracker_thread = threading.Thread(target = tracker.start)
tracker_thread.start()
hand_slicing = False
hand_slicing_path=[]
lastx= 1000
lasty= 1000
lastt= 0

while run:
    CS = 0 #current score

    while level == 1 and run:
        current_time = time.time()
        ButtonLV1()  
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if event.type == MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                x, y = pos
                print(str(x)+" "+str(y))
                if 105*X < x < 215*X and 100*Y < y < 140*Y : #START on LV1
                    level = 2
                    lastt = time.time()
                if 270*X < x < 310*X and 200*Y < y < 240*Y : #Quit on LV1
                    run = False
                    lastt = time.time()
                    print("Level 1 Quit Pressed")
                if 10*X < x < 40*X and 100*Y < y < 140*Y : #< on LV1
                    bg -= 1
                    if bg == 0:
                        bg = 4
                    lastt = time.time()
                    print("Left Pressed")
                    break
                if 280*X < x < 310*X and 100*Y < y < 140*Y : #> on LV1
                    bg += 1
                    if bg == 5:
                        bg = 1
                    lastt = time.time()
                    print("Right Pressed")
                    break
        
        center = tracker.get_center()
        x,y = center 
        if(x!=None and y!=None):
            hand_slicing = True
            hand_slicing_path.append(((80*4*X-x,y), time.time()))
            x=80*4*X-x
            if -50<=x-lastx<=50 and -50<=y-lasty<=50:
                if(time.time()-lastt>1):
                    if 105*X < x < 215*X and 100*Y < y < 140*Y : #START on LV1
                        level = 2
                        lastt = time.time()
                    if 270*X < x < 310*X and 200*Y < y < 240*Y : #Quit on LV1
                        run = False
                        lastt = time.time()
                        print("Level 1 Quit Pressed")
                    if 10*X < x < 40*X and 100*Y < y < 140*Y : #< on LV1
                        bg -= 1
                        if bg == 0:
                            bg = 4
                        lastt = time.time()
                        print("Left Pressed")
                        break
                    if 280*X < x < 310*X and 100*Y < y < 140*Y : #> on LV1
                        bg += 1
                        if bg == 5:
                            bg = 1
                        lastt = time.time()
                        print("Right Pressed")
                        break
            else:
                lastx = x
                lasty = y
                lastt = time.time()
        else:
            hand_slicing = False
    
        if hand_slicing:
            hand_slicing_path = [(pos, t) for pos, t in hand_slicing_path if current_time - t < 0.3]
            if len(hand_slicing_path) > 1:
                pygame.draw.lines(screen, (0, 0, 255), False, [pos for pos, _ in hand_slicing_path], 10)
        pygame.display.flip()
        
    while level == 2 and run:
        current_time = time.time()
        ButtonLV2()  
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if event.type == MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                x, y = pos
                print(str(x)+" "+str(y))
                if 120*X < x < 195*X and 80*Y < y < 100*Y : #easy on LV2
                    level = 3
                    hard = False
                    CDS = time.time()
                    lastt = time.time()
                    print("Easy Mode")
                if 120*X < x < 195*X and 140*Y < y < 160*Y : #hard on LV2
                    CDS = time.time()
                    hard = True
                    level = 3
                    lastt = time.time() 
                    print("Hard Mode")
                if 265*X < x < 310*X and 200*Y < y < 240*Y : #Back on LV2
                    level = 1
                    lastt = time.time()
                    print("Level 2 Back Pressed")
                    
        center = tracker.get_center()
        x,y = center 
        if(x!=None and y!=None):
            hand_slicing = True
            hand_slicing_path.append(((80*4*X-x,y), time.time()))
            x=80*4*X-x
            if -50<=x-lastx<=50 and -50<=y-lasty<=50:
                if(time.time()-lastt>1):
                    if 120*X < x < 195*X and 80*Y < y < 100*Y : #easy on LV2
                        level = 3
                        hard = False
                        CDS = time.time()
                        print("Easy Mode")
                    if 120*X < x < 195*X and 140*Y < y < 160*Y : #hard on LV2
                        CDS = time.time()
                        hard = True
                        level = 3 
                        print("Hard Mode")
                    if 265*X < x < 310*X and 200*Y < y < 240*Y : #Back on LV2
                        level = 1
                        print("Level 2 Back Pressed")
            else:
                lastx = x
                lasty = y
                lastt = time.time()
        else:
            hand_slicing = False
    
        if hand_slicing:
            hand_slicing_path = [(pos, t) for pos, t in hand_slicing_path if current_time - t < 0.3]
            if len(hand_slicing_path) > 1:
                pygame.draw.lines(screen, (0, 0, 255), False, [pos for pos, _ in hand_slicing_path], 10)
        pygame.display.flip()       
                 
    while level == 3 and run:
        gametime = time.time() - CDS #time spend in LV3
        current_time = time.time()
        ButtonLV3(gametime)
        if gametime > CD+3:
            level = 4
            if HS < CS: HS = CS
            for balloon in balloons[:]: balloons.remove(balloon)
            for animation in animations[:]: animations.remove(animation)
            print("Game End")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                slicing = True
                pos = pygame.mouse.get_pos()
                x, y = pos
                print(str(x)+" "+str(y))
                if 280*X < x < 310*X and 200*Y < y < 240*Y : #End on LV3
                    level = 4
                    if HS < CS: HS = CS
                    for balloon in balloons[:]: balloons.remove(balloon)
                    for animation in animations[:]: animations.remove(animation)
                    print("Level 3 End Pressed")
                for balloon in balloons[:]:
                    if balloon.rect.collidepoint(pos):
                        animation_type = 'water' if balloon.color != 'red' else 'bomb'
                        animations.append(Animation(balloon.rect.center, animation_type))
                        balloons.remove(balloon)
                        CS += balloon.score
            elif event.type == pygame.MOUSEBUTTONUP:
                slicing = False
            elif event.type == pygame.MOUSEMOTION and slicing:
                slicing_path.append((pygame.mouse.get_pos(), current_time))
                for balloon in balloons[:]:
                    if any(balloon.rect.collidepoint(pos) for pos, _ in slicing_path):
                        animation_type = 'water' if balloon.color != 'red' else 'bomb'
                        animations.append(Animation(balloon.rect.center, animation_type))
                        balloons.remove(balloon)
                        CS += balloon.score
                       
        center = tracker.get_center()
        x,y = center 
        if(x!=None and y!=None):
            hand_slicing = True
            hand_slicing_path.append(((80*4*X-x,y), time.time()))
            x=80*4*X-x
            if -50<=x-lastx<=50 and -50<=y-lasty<=50:
                if(time.time()-lastt>1):
                    if 280*X < x < 310*X and 200*Y < y < 240*Y : #End on LV3
                        level = 4
                        if HS < CS: HS = CS
                        for balloon in balloons[:]: balloons.remove(balloon)
                        for animation in animations[:]: animations.remove(animation)
                        lastt = time.time()
                        print("Level 3 End Pressed")
            else:
                lastx = x
                lasty = y
                lastt = time.time()
            for balloon in balloons[:]:
                if any(balloon.rect.collidepoint(pos) for pos, _ in hand_slicing_path):
                    animation_type = 'water' if balloon.color != 'red' else 'bomb'
                    animations.append(Animation(balloon.rect.center, animation_type))
                    balloons.remove(balloon)
                    CS += balloon.score
        else:
            hand_slicing = False
        

    
        if slicing:
            slicing_path = [(pos, t) for pos, t in slicing_path if current_time - t < 0.2]
            if len(slicing_path) > 1:
                pygame.draw.lines(screen, (255, 0, 0), False, [pos for pos, _ in slicing_path], 10)
        if hand_slicing:
            hand_slicing_path = [(pos, t) for pos, t in hand_slicing_path if current_time - t < 0.3]
            if len(hand_slicing_path) > 1:
                pygame.draw.lines(screen, (0, 0, 255), False, [pos for pos, _ in hand_slicing_path], 10)
            
        n = 45/X if hard == True else 90/X
        if random.randint(1, n) == 1:
            balloons.append(Balloon())
        
        if gametime > 3:
           for balloon in balloons:
               balloon.move()
               balloon.draw()
            
        for animation in animations[:]:
            animation.draw(screen)
            if animation.opacity <= 243:
                animations.remove(animation)
                    
        pygame.display.flip()
        
    while level == 4 and run:
        current_time = time.time()
        ButtonLV4()  
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if event.type == MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                x, y = pos
                print(str(x)+" "+str(y))
                if 45*X < x < 135*X and 150*Y < y < 170*Y : #Play Again on LV4
                    level = 3
                    CDS = time.time()
                    print("Play Again")
                if 155*X < x < 300*X and 150*Y < y < 170*Y : #Another Difficulty on LV4
                    level = 2 
                    print("Difficulty Selection")
                if 260*X < x < 310*X and 200*Y < y < 240*Y : #Home on LV4
                    level = 1
                    print("Level 4 Home Pressed")
                    
        center = tracker.get_center()
        x,y = center 
        if(x!=None and y!=None):
            hand_slicing = True
            hand_slicing_path.append(((80*4*X-x,y), time.time()))
            x=80*4*X-x
            if -50<=x-lastx<=50 and -50<=y-lasty<=50:
                if(time.time()-lastt>1):
                    if 45*X < x < 135*X and 150*Y < y < 170*Y : #Play Again on LV4
                        level = 3
                        CDS = time.time()
                        lastt = time.time()
                        print("Play Again")
                    if 155*X < x < 300*X and 150*Y < y < 170*Y : #Another Difficulty on LV4
                        level = 2 
                        lastt = time.time()
                        print("Difficulty Selection")
                    if 260*X < x < 310*X and 200*Y < y < 240*Y : #Home on LV4
                        level = 1
                        lastt = time.time()
                        print("Level 4 Home Pressed")
            else:
                lastx = x
                lasty = y
                lastt = time.time()
        else:
            hand_slicing = False
    
        if hand_slicing:
            hand_slicing_path = [(pos, t) for pos, t in hand_slicing_path if current_time - t < 0.3]
            if len(hand_slicing_path) > 1:
                pygame.draw.lines(screen, (0, 0, 255), False, [pos for pos, _ in hand_slicing_path], 10)
        pygame.display.flip()       
       
screen.fill(BLACK)
pygame.display.flip()
tracker.running = False
tracker_thread.join()
pygame.quit()
GPIO.cleanup()
