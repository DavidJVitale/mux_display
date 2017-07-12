#!/usr/bin/env python

"""
MUX DISPLAY v0.1

A tkinter GUI program that interfaces with a 328p 
microcontroller (Arduino) program. Displays the 0-5V analog signal 
being fed into the device, outputs 8 bits of information over PORTB.
In this case, used to control a MUX. Interfaces over serial.

Author:  - David Vitale
         - DJH (see GraphingWidget class)
         - Dr. R.A. Scheidt (see GraphingWidget class)
Date:    - 2017-12-07
Contact: - davidjosephvitale(at)gm4il.com ('a' instead of '4')
"""

import tkinter
import threading
import time
import sys
import re

from serial import Serial, SerialException
from traceback import print_exc
from tkinter import messagebox

#not controlled in this program; controlled via 328p program
ANALOG_SAMPLING_RATE = 1000
BAUD_RATE = 115200

#different states of control_modes
CYCLING_MODE = 0
SINGLE_SELECT_MODE = 1

#conversion constants from seconds to cycling units
CYCLING_UNITS_PER_S = 15624 #number of timer cycles per second
S_PER_MS = 0.001

#bounds of cycle_period (can't be checked in arduino)
CYCLING_PERIOD_LOWER_UNIT = 1
CYCLING_PERIOD_UPPER_UNIT = 0xFFFE

#error messages for serial port connection errors 
BASE_COM_ERROR            = "Check all wired connections, make sure you can"\
                            " view the arduino/microcontroller in your device"\
                            " manager as a serial device, and make sure no"\
                            " other program is using the device. (See the"\
                            " manual for more information)"
NO_COM_PORTS_LEFT_MESSAGE = "Device not found, "\
                            "no COM ports left to check for. " + BASE_COM_ERROR
NO_COM_PORT_ERROR_MESSAGE = "Device not found, "\
                            "no COM ports detected. " + BASE_COM_ERROR

#Global widgets needed accross functions
my_graphing_widget = None

#Global variables needed across functions
control_mode = CYCLING_MODE
ser = None
counter = 0
points = []
start_time = 0

class Point:
    """Simple class to hold a time and a y value"""
    def __init__(self, t, y):
        self.t = t
        self.y = y

class GraphingWidget(tkinter.Canvas):
    """The original class written by "DJH", implemented in David Vitale's
    BIEN4280 course. This class was given to David by Dr. R.A. Scheidt, and
    was modified to include moving time labels and some other functionality.
    Here is the original comment header on top of the unmodified source
    file when given to David:
        #!/usr/bin/env python
        # vim: expandtab ts=4 
        # Simple example to graph a sine wave now using tkinter
        # DJH 11/3/2010
    """
    def __init__(self, master, num_series=1,
                 history=1, y_min=-1, y_max=1, **options):
        """Initialize a new drawing widget. Customizeable parameters:
           1) num_series -- the number of simultaneous plots to display
           1) history -- the history time (in seconds)
           2) y_min -- the minimum y value
           3) y_max -- the maximum y value"""

        tkinter.Canvas.__init__(self, master, background="black", **options)
        # Make an internal sempahore (mutex)
        self.semaphore = threading.Semaphore(1)

        # Make sure num_series is valid
        try:
            num_series = int(num_series)
        except:
            raise RuntimeError('num_series must be an integer')
        if num_series < 1:
            raise RuntimeError('Cannot have less than 1 series')
        # Make sure time is valid is valid
        try:
            history = float(history)
        except:
            raise RuntimeError('history must be a float')
        if history <= 0:
            raise RuntimeError('Cannot display zero or negative amount of time') 
        # Check y_min and y_max
        try:
            y_min = float(y_min)
            y_max = float(y_max)
        except:
            raise RuntimeError('y_min and y_max must be floats')
        if y_min == y_max:
            raise RuntimeError('y_min and y_max cannot be identical')
        # If y_max < y_min, swap the values
        if y_max < y_min:
            temp = y_max
            y_max = y_min
            y_min = temp        
        # Save the necessary values
        self.num_series = num_series
        self.history = history
        self.y_max = y_max
        self.y_min = y_min

        # Create empty FIFO queues
        self.enabled = []
        self.t_values = []
        self.y_values = []
        self.line_colors = []
        self.line_widths = []
        self.has_label = []
        for i in range(0, self.num_series):
            # Create the empty lists (i.e. a list of lists)
            self.t_values.append([])
            self.y_values.append([])
            self.has_label.append([])
            self.enabled.append(True) # All plots enabled by default
            self.line_colors.append("green") # Default color is green
            self.line_widths.append(1) # Default width is 1 pixel

        # Connect the expose event
        self.bind("<Expose>", self.expose_event)

        # Setup widget to animate every 1/24th of a second
        self.animate()
 
    def disable_series(self, series=0):
        """Disable a series"""
        try:
            series = int(series)
        except:
            raise RuntimeError('Series must be an integer')
        if series < 0 or series >= self.num_series:
            raise RuntimeError('Invalid series number in disable_series')
        self.enabled[series] = False
        
    def enabled_series(self, series=0):
        """Enabled a series"""
        try:
            series = int(series)
        except:
            raise RuntimeError('Series must be an integer')
        if series < 0 or series >= self.num_series:
            raise RuntimeError('Invalid series number in enabled_series')
        self.enabled[series] = True

    def animate(self):
        self.plot_tk()
        self.update_idletasks()
        # Call to animate faster than 10 fps
        self.master.after(30, self.animate) 

    def expose_event(self, event):
        self.plot_tk()
    
    def plot_tk(self):
        if not ser:
            return
        # Lambda function (given width & height)
        to_y_coordinate = lambda y: height - (y - self.y_min) * height / \
                                    (self.y_max - self.y_min)
        to_t_coordinate = lambda t: width - (base_time - t) * width / \
                                    self.history

        # Delete all previously plotted items
        self.delete("all")
       
        # Get width and height
        width = self.winfo_width()
        height = self.winfo_height()
 
        # Store the base time
        base_time = time.time()
        
        # Pop all unnecessary values (OLD) off of each queue
        self.semaphore.acquire()
        for i in range(0, self.num_series):
            while len(self.t_values[i]) > 0 and \
                (self.t_values[i][0] + self.history < base_time):
                self.t_values[i] = self.t_values[i][1:]
                self.y_values[i] = self.y_values[i][1:] # Remove 0th value
                self.has_label[i] = self.has_label[i][1:]
            # Make sure that x and y values are the same length
            if len(self.t_values[i]) != len(self.y_values[i]):
                raise RuntimeError('Invalid lengths for t and y values')
        self.semaphore.release()
         # Create the translation from pixels to coordinates
        # (0, y_min) ----------- (history, y_min)
        #   |                  |
        #   |                  |
        # (0, y_max) ----------- (history, y_max)

        for i in range(1,6):
            self.create_line(0,to_y_coordinate(i),
                             5,to_y_coordinate(i),
                             fill="white",
                             width=3)
            self.create_text(14, to_y_coordinate(i),
                             text=str(i),
                             fill="white",
                             font="-weight bold")
            self.create_line(23,to_y_coordinate(i),
                             26,to_y_coordinate(i),
                             fill="white",
                             width=3)

        # Start to plot each series
        for i in range(0, self.num_series):
            # Check if we are enabled
            if self.enabled[i] == False:
                continue # Move onto next plot
            line_coords = []
            for j in range(0, len(self.y_values[i])):
                #cairo_context.line_to(to_t_coordinate(self.t_values[i][j]), 
                #    to_y_coordinate(self.y_values[i][j]))
                line_coords.append(to_t_coordinate(self.t_values[i][j]))
                line_coords.append(to_y_coordinate(self.y_values[i][j]))

                if self.has_label[i][j]:
                    elapsed = "{0:.2f}".format(time.time() - start_time)
                    self.create_text(to_t_coordinate(self.t_values[i][j]),
                                 to_y_coordinate(0.3),
                                 text = self.has_label[i][j],
                                 fill="white",
                                 font="-weight bold")
                    self.create_line(to_t_coordinate(self.t_values[i][j]),
                                     to_y_coordinate(0),
                                     to_t_coordinate(self.t_values[i][j]),
                                     to_y_coordinate(0.15),
                                     fill="white",
                                     width=3)
                    self.create_line(to_t_coordinate(self.t_values[i][j]),
                                     to_y_coordinate(0.45),
                                     to_t_coordinate(self.t_values[i][j]),
                                     to_y_coordinate(0.6),
                                     fill="white",
                                     width=3)

            if len(line_coords) >= 4:
                self.create_line(*tuple(line_coords), fill=self.line_colors[i],
                width=self.line_widths[i])


    def change_series_color(self, color, series=0):
        """Change the color of a series"""
        try:
            series = int(series)
        except:
            raise RuntimeError('Series must be an integer')
        if series < 0 or series >= self.num_series:
            raise RuntimeError('Invalid series number in change_series_color')
        self.line_colors[series] = color

    def change_series_width(self, width, series=0):
        """Change the width of a given series"""
        try:
            series = int(series)
        except:
            raise RuntimeError('Series must be an integer')
        if series < 0 or series >= self.num_series:
            raise RuntimeError('Invalid series number in change_series_color')
        self.line_widths[series] = width      

    def add_y_value(self, value, series=0):
        """Adds a new y-value to the given series"""
        # Make sure value is a float
        global counter
        counter = counter + 1
        try:
            value = float(value)
        except:
            raise RuntimeError('Y-values must be floats')
        try:
            series = int(series)
        except:
            raise RuntimeError('Series must be an integer')
        if series < 0 or series >= self.num_series:
            raise RuntimeError('Invalid series number in add_y_value')
        # Append the necessary values to the queue (FIFO)
        self.semaphore.acquire()
        self.y_values[series].append(value)
        self.t_values[series].append(time.time()) # The current time
        if counter % ANALOG_SAMPLING_RATE == 0:
            self.has_label[series].append("{0:.2f}".format(time.time()
                                                           - start_time))
        else:
            self.has_label[series].append("")
        self.semaphore.release()

def serial_manager_thread():
    """The thread that reads lines from the serial connection, checking for
    errors, parse analog data onto graph, add data to global data point list
    for eventual file writing, etc.
    """
    global call_beep, alarm_state, points
    import math
    points_accu = []
    while True:  
        if ser:
            buf = str(ser.readline())
            if "ERR" in buf:
                for i in range(0,3): #print out information after the error:
                    buf += str(ser.readline())
                buf = buf.replace("\\r","").replace("'","").replace("b", "")
                buf = buf.replace("\\n","\n")
                print(buf)
                messagebox.showwarning("","Microcontroller threw this error:"
                                       "\n\n{}\n\nYou might need to power "\
                                       "cycle the device".format(buf))

            try:
                stream = re.sub("\D", "", buf) #only accept digits
            except Exception:
                pass
            if stream and stream.isdigit():# and (int(stream) <= 5):
                val = (int(stream) / 1024) * 5
                sys.stdout.write("\rval->{0:.2f}".format(val))
                if(val <= 5): #no value should ever be greater than 5:
                    points_accu.append(val)
                    points.append(Point(t=time.time()-start_time, y=val))

                    my_graphing_widget.add_y_value(val, series=0)

def export_to_file():
    """Takes all global points that have been saved for every data pull,
    writes to a file
    """
    global points
    dirname = "exported_files/"
    filename = str(time.time()) + ".csv"

    try:
        f = open(dirname + filename, "w")
    except Exception: #if dir isn't found, fallback
        f = open(filename, "w")

    for point in points:
        f.write("{}\t{}\n".format(point.t, point.y))
    f.close()
    points = []
    messagebox.showinfo("","{} written successfully!".format(filename))

def serial_ports():
    """ Lists serial port names. Pulled from http://stackoverflow.com/questions/
        12090503/listing-available-com-ports-with-python
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = Serial(port)
            s.close()
            result.append(port)
        except (OSError, SerialException):
            pass
    return result


def query_user_for_correct_serial_port():
    """Checks for all available PORT devices, querying the user which one
    is the arduino/correct device. Returns the string representation of it
    """
    available_serial_ports = serial_ports()
    if not available_serial_ports:
        messagebox.showerror("",NO_COM_PORT_ERROR_MESSAGE)
        exit(0)
    for port in available_serial_ports:
        if "yes" == messagebox.askquestion("",
                                          "Connect to {} device?".format(port)):
            return port
    messagebox.showerror("",NO_COM_PORTS_LEFT_MESSAGE)
    exit(0)

def set_connection():
    """Actually connects to the serial device, allowing the graph data
    to be drawn and commands to be sent to the device
    """
    com_port = query_user_for_correct_serial_port()
    baud_rate = str(BAUD_RATE)
 
    global ser, start_time, points
    points = []
    start_time = time.time()
    print("attempting serial connection...")
    try:
        print("com={}, baud={}".format(com_port, baud_rate))
        ser = Serial(com_port, baud_rate)
    except Exception:
        print("something went wrong in configuring serial...")
        print_exc()

def change_graph_speed():
    """What happens when the graph width button is pressed.
    'history' is how much history is stored in the graph. When it is redrawn,
    the less history, the faster the graph moves
    """
    global my_graphing_widget
    graph_width_in_ms = graph_speed_text.get().strip()
    history_length = float(graph_width_in_ms) / 1000.0
    my_graphing_widget.history = history_length

def send_single_select_command():
    """What happens when the single select mode button is pressed. Get all
    Entry widget text that the user inputted, then send the command to the 
    arduino to set the arduino in the user configured format
    """
    channel_num_str = single_select_entry.get().strip()
    command = ("qqq"    #exits any open windows
              "s"       #enter single select mode
              "{}"      #the channel_number the user entered
              "q"       #tell the prompt we're done
              "").format(channel_num_str)
    if ser:
        ser.write(command.encode('utf-8'))

def send_cycling_command():
    """What happens when the cycling mode button is pressed. Get all Entry 
    widget text that the user inputted, do some conversions, check for bounds,
    then send the command to the arduino to set the arduino in the user
    configured format
    """
    lower_bound_str = lower_bound_entry.get().strip()
    upper_bound_str = upper_bound_entry.get().strip()
    cycling_period_ms = float(cycling_period_entry.get().strip())
    cycling_units = int(cycling_period_ms * S_PER_MS * CYCLING_UNITS_PER_S)

    if (cycling_units < CYCLING_PERIOD_LOWER_UNIT
     or cycling_units > CYCLING_PERIOD_UPPER_UNIT):
            messagebox.showwarning("", "Cycling Period needs to be between 1ms"\
                                   " and 4000ms. No changes made.")
            return

    command = ("qq"     #exits any open windows
              "l"       #enter lower_bound changing
              "{}"      #the lower_bound the user entered
              "q"       #tell the prompt we're done
              "u"       #enter upper_bound changing
              "{}"      #the upper_bound the user entered
              "q"       #tell the prompt we're done
              "p"       #enter cycling_period changing
              "{}"      #the cycling_period the user entered
              "q"       #tell the prompt we're done
              "c"       #start the cycling!
              "").format(lower_bound_str,
                         upper_bound_str,
                         cycling_units)
    if ser:
        ser.write(command.encode('utf-8'))

def control_mode_button_press():
    """What is pressed when the control mode toggle button is pressed
    """
    global control_mode
    if control_mode == CYCLING_MODE:
        control_mode = SINGLE_SELECT_MODE
    elif control_mode == SINGLE_SELECT_MODE:
        control_mode = CYCLING_MODE
    update_gui_based_off_control_mode()

def update_gui_based_off_control_mode():
    """Unveil the correct controls depending on what the current control_mode
    is. Hide the not-in-use controls
    """
    if control_mode == CYCLING_MODE:
        cover_for_cycling.place_forget()
        cover_for_single.place(relx=1, rely=1, x=0, y=0, anchor=tkinter.SE)
        single_select_label.config(background=cycle_mode_label.cget("bg"))
        cycle_mode_label.config(background="orange")
    elif control_mode == SINGLE_SELECT_MODE:
        cover_for_single.place_forget()
        cover_for_cycling.place(relx=0, rely=1, x=0, y=0, anchor=tkinter.SW)
        cycle_mode_label.config(background=single_select_label.cget("bg"))
        single_select_label.config(background="orange")

def close_program():
    sys.exit(0)

if __name__ == '__main__':
    """The main functionality that starts when the program is run.
    Initialize all GUI components, connect to serial, start threads.
    """
    #root tkinter properties (name, window, icon, frame, etc.)
    root = tkinter.Tk()
    root.protocol('WM_DELETE_WINDOW', close_program)
    root.wm_title("MUX DISPLAY v0.1")
    root.state('zoomed')
    frame = tkinter.Frame(root, width=1, height=1)
    frame.pack(fill=tkinter.BOTH, expand=tkinter.YES)
    root.iconbitmap("icon.ico")

    #file management widgets
    file_button = tkinter.Button(frame,
                                 text="Export To File",
                                 justify=tkinter.RIGHT,
                                 command=export_to_file,
                                 font="-weight bold",
                                 bg="grey")
    file_button.place(relx=1, x=0, y=0, anchor=tkinter.NE)

    #graph speed/graph width widgets
    graph_speed_label = tkinter.Label(frame, text="Graph Width (ms)",
                                      font="-weight bold")
    graph_speed_label.place(relx=0, x=50, y=4, anchor=tkinter.NW)
 
    graph_speed_text = tkinter.Entry(frame, width=6,
                                    font="-weight bold")
    graph_speed_text.place(relx=0, x=190, y=6, anchor=tkinter.NW)
    graph_speed_text.insert(tkinter.END, "1000")

    update_button = tkinter.Button(frame,
                                   text="SET",
                                   justify=tkinter.RIGHT,
                                   command=change_graph_speed,
                                   font="-weight bold",
                                   bg="grey")
    update_button.place(relx=0, x=240, y=0, anchor=tkinter.NW)

    #graph and axis widgets
    graph_label = tkinter.Label(frame, text = "Voltage (V) vs. Time (s)",
                                 font="-weight bold",
                                 borderwidth=8)
    graph_label.pack(side=tkinter.TOP)

    y_label = tkinter.Label(frame,
                            text = "Volts\n(V)",
                            font="-weight bold")
    y_label.pack(side=tkinter.LEFT)

    my_graphing_widget = GraphingWidget(frame, num_series=1,
                                        history=1, y_min=0, y_max=6)
    my_graphing_widget.pack(fill=tkinter.BOTH,
                            expand=tkinter.YES,
                            side=tkinter.TOP)
    my_graphing_widget.change_series_color("red", 0)
    my_graphing_widget.change_series_width(5, 0)

    x_label = tkinter.Label(frame, text = "Time (s)",
                                 font="-weight bold")
    x_label.pack(side=tkinter.TOP)

    #mode changing area widgets
    cycle_mode_label = tkinter.Label(frame, text =
    "CYCLE MODE",
                                 font="-weight bold")
    cycle_mode_label.pack(side=tkinter.TOP)

    mode_button = tkinter.Button(frame,
                                 text="CHANGE MODE",
                                 command=control_mode_button_press,
                                 font="-weight bold",
                                 bg="gray")
    mode_button.pack(side=tkinter.TOP)

    single_select_label = tkinter.Label(frame, text =
    "SINGLE SELECT MODE",
                                 font="-weight bold")
    single_select_label.pack(side=tkinter.TOP)

    #cycle mode widgets
    lower_bound_label = tkinter.Label(frame, text="Lower",
                                      font="-weight bold")
    lower_bound_label.pack(side=tkinter.LEFT)
 
    lower_bound_entry = tkinter.Entry(frame, width=3,
                                    font="-weight bold")
    lower_bound_entry.pack(side=tkinter.LEFT)
    lower_bound_entry.insert(tkinter.END, "0")

    upper_bound_label = tkinter.Label(frame, text="Upper",
                                      font="-weight bold")
    upper_bound_label.pack(side=tkinter.LEFT)
 
    upper_bound_entry = tkinter.Entry(frame, width=3,
                                      font="-weight bold")
    upper_bound_entry.pack(side=tkinter.LEFT)
    upper_bound_entry.insert(tkinter.END, "15")

    cycling_period_label = tkinter.Label(frame, text="Cycling Period (ms)",
                                      font="-weight bold")
    cycling_period_label.pack(side=tkinter.LEFT)
 
    cycling_period_entry = tkinter.Entry(frame, width=5,
                                      font="-weight bold")
    cycling_period_entry.pack(side=tkinter.LEFT)
    cycling_period_entry.insert(tkinter.END, "100")

    cycle_button = tkinter.Button(frame,
                                  text="SET",
                                  command=send_cycling_command,
                                  font="-weight bold",
                                  bg='gray')
    cycle_button.pack(side=tkinter.LEFT)

    #Single Select Mode Widgets
    blank_label = tkinter.Label(frame, text="                    ",
                                        font="-weight bold")
    blank_label.pack(side=tkinter.RIGHT)

    single_button = tkinter.Button(frame,
                                  text="SET",
                                  command=send_single_select_command,
                                  font="-weight bold",
                                  bg='gray')
    single_button.pack(side=tkinter.RIGHT)

    single_select_entry = tkinter.Entry(frame, width=3,
                                      font="-weight bold")
    single_select_entry.pack(side=tkinter.RIGHT)
    single_select_entry.insert(tkinter.END, "0")

    channel_num_label = tkinter.Label(frame, text="Channel #",
                                      font="-weight bold")
    channel_num_label.pack(side=tkinter.RIGHT)

    screen_width = root.winfo_width()
    screen_height = root.winfo_height()

    #blank canvases to cover up modes when not in use
    cover_for_single = tkinter.Canvas(frame,
                                      width=int(screen_width/3),
                                      height=int(screen_height/8))
    cover_for_cycling = tkinter.Canvas(frame,
                                       width=int(screen_width/2.5),
                                       height=int(screen_height/8))
    cover_for_single.place(relx=1, rely=1, x=0, y=0, anchor=tkinter.SE)
    cover_for_cycling.place(relx=0, rely=1, x=0, y=0, anchor=tkinter.SW)
    update_gui_based_off_control_mode()

    #attempt to connect to device before starting program
    set_connection()

    #initialize threads, start the program!
    t = threading.Thread(target=serial_manager_thread)
    t.setDaemon(True) # It is a daemon
    t.start()   

    root.mainloop()

    t.join()