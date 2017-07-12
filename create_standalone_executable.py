#run this script in the windows CMD prompt like this:
#py -3.4 create_standalone_executable.py py2exe

from distutils.core import setup
import py2exe

setup(console=['mux_display.py'])