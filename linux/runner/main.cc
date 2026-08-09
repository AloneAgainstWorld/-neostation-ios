#include "my_application.h"

// Fix for "Xlib is not thread-safe" error in AppImage
#include <X11/Xlib.h>

int main(int argc, char** argv) {
  // Initialize X11 threading support before GTK/GDK initialization
  // This MUST be called before any other Xlib calls
  XInitThreads();
  
  g_autoptr(MyApplication) app = my_application_new();
  return g_application_run(G_APPLICATION(app), argc, argv);
}
