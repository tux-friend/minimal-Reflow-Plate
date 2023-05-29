import machine, time
from machine import Pin, Timer, SoftI2C
from ssd1306 import SSD1306_I2C
from max6675 import MAX6675

i2c = SoftI2C(scl=Pin(3),sda=Pin(4))
button = Pin(8, Pin.IN, Pin.PULL_UP)
oled = SSD1306_I2C(128,64, i2c)

sck = Pin(2, Pin.OUT)
cs = Pin(1, Pin.OUT)
so = Pin(0, Pin.IN)
ssr = Pin(6, Pin.OUT)
tk = MAX6675(sck, cs, so)

# Reflow profile Sn63/Pb37, (duration, temp)

profile = [
    (50,100),
    (45,125),
    (45,150),
    (30,183),
    (60,235),
    (30,183),
    (60,100)
]

# Variables for PID control
last_error = 0
integral = 0
duration = 0
for step in range(len(profile)):
    duration += profile[step][0]
time_step = 0.2

#Button press functions + debounce
def on_pressed(timer):
    global butstate
    butstate = (butstate + 1) % 2

def debounce(pin):
    timer.init(mode=Timer.ONE_SHOT, period=200, callback=on_pressed)

timer = Timer(0)
button.irq(debounce, Pin.IRQ_RISING)

def get_temp():
    temp = tk.read()
    return temp

def control_temp(setpoint, temp):
    global last_error, integral
    if temp<=150:
        kp = 100.0
        ki = 0.025
        kd = 20.0
    else:
        kp = 300.0
        ki = 0.05
        kd = 350.0
    # Calculate the error
    error = setpoint - temp
    # Calculate the integral term
    integral += error
    # Calculate the derivative term
    derivative = error - last_error
    # Calculate the control output using PID equation
    output = kp * error + ki * integral + kd * derivative
    # Update the last error
    last_error = error
    # Limit the control output to the range [0, 1]
    if temp >= setpoint:
        output = 0
    else:
        output = max(0, min(1, output))        
    return output

def control_ssr(output):
    if output > 0:
        ssr.on()  # Turn on SSR
    else:
        ssr.off()  # Turn off SSR
        
def disp_start():
    t = tk.read()
    oled.fill(0)
    oled.text("Heat Plate",25,3)
    oled.text("Press button",15,17)
    oled.text("to start", 35, 27)
    oled.text("Reflow process", 10,37)
    if t>70:
        oled.text("HOT!!!",80,55)
        oled.invert(1)
    else:
        oled.invert(0)
    disp_temp()

def disp_temp():
    t = tk.read()
    oled.fill_rect(0,55,80,10,0)
    oled.text("T:%.1fC" % t, 0, 55)
    oled.show()

def disp_graph():
    oled.fill(0)
    oled.invert(0)
    oled.hline(0,63,128,1)
    oled.vline(0,10,54,1)
    graph_width = 126
    graph_height = 54
    time_scale = graph_width / duration
    temp_scale = graph_height / 180.0
    x = 0
    for i in range(len(profile)):
        x += int(profile[i][0]*time_scale)
        y = int(graph_height-profile[i][1]*temp_scale+33)
        oled.hline(x-2,y,5,1)
        oled.vline(x, y-2,5,1)
    oled.show()

def disp_cool():
    global butstate
    t = tk.read()
    oled.fill(0)
    oled.text("Cooling down",15,15)
    oled.text("Please wait", 20, 30)
    if t>70:
        oled.text("HOT!!!",80,55)
        oled.invert(1)
    else:
        oled.invert(0)
    disp_temp()

def disp_pixel(temp, tt):
    oled.fill_rect(0,0,128,10,0)
    oled.text("T:%.1fC" % temp, 0, 0)
    oled.text("{}s".format(tt), 90, 0)
    # Plot temperature vs. time graph
    graph_width = 126
    graph_height = 54
    time_scale = graph_width / duration
    temp_scale = graph_height / 180.0
    x = int(tt * time_scale)
    y = int(graph_height - temp * temp_scale+33)
    oled.pixel(x, y, 1)
    oled.show()
 
def disp_stop():
    oled.fill(0)
    oled.text("Reflow process",8,15)
    oled.text("stopped!", 30,30)
    for i in range(10):
        disp_temp()
        time.sleep(0.5)

def disp_finish():
    oled.fill(0)
    oled.text("Reflow process",8,15)
    oled.text("finished!", 30,30)
    for i in range(10):
        disp_temp()
        time.sleep(0.2)

def reflow():
    a = time.localtime()
    open('temp_'+str(a[3])+str(a[4])+'.csv','w').close()
    data = open('temp_'+str(a[3])+str(a[4])+'.csv','w')
    global butstate
    disp_graph()
    butstate = 0
    temp = []
    tt = 0
    for step in range(len(profile)):
        setpoint = profile[step][1]
        duration = profile[step][0]
        
        d = int(duration/time_step)
        temp = [0] * d
        set_original = setpoint
        if setpoint <= 100:
            setpoint_corr = 0.6*setpoint - 7.5
        elif setpoint > 100 and setpoint <= 150:
            setpoint_corr = 0.9*setpoint
        elif setpoint > 150 and setpoint <= 200:
            setpoint_corr = setpoint - 5.0
        else:
            setpoint_corr = setpoint
    
        for i in range(d):
            t = get_temp()
            data.write(str(tt)+','+str(t)+','+str(set_original)+'\n')
            if i <= int(0.35*d):
                setpoint = setpoint_corr
            elif i > int(0.35*d) and i <= (int(0.35*d)+11):
                setpoint = set_original - 3.0
            elif i > (int(0.35*d)+11) and i <= int(0.7*d):
                setpoint = setpoint_corr
            else:
                setpoint = set_original
            power = control_temp(setpoint, t)
            control_ssr(power)
            if (i % int(1/time_step)) == 0:
                disp_pixel(int(t), int(tt)+1)
            time.sleep(time_step)
            tt += time_step
            if butstate == 1:
                control_ssr(0)
                oled.fill(0)
                oled.text("Stopped reflow!",5,20)
                oled.show()
                time.sleep(4)
                butstate = 0
                return
    data.close()
    control_ssr(0)
    disp_finish()
    time.sleep(5)

butstate = 0
disp_start()
temp_max = 50.0
control_ssr(0)
while True:
    temp = tk.read()
    if butstate == 0:
        control_ssr(0)
        disp_start()
    elif butstate == 1 and temp<temp_max:
        reflow()
    elif butstate == 1 and temp>temp_max:
        control_ssr(0)
        for i in range(10):
            disp_cool()
            time.sleep(0.2)
        butstate = 0
    else:
        butstate = 0
