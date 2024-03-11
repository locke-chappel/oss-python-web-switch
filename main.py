import machine

import app
import settings

try:
    app.Main()
except Exception as ex:
    import sys
    
    if settings.DEBUG:
      sys.print_exception(ex)
      
    machine.reset()
