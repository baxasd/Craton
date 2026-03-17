import os
import sys
import webbrowser
from threading import Timer
import streamlit.web.cli as stcli

def open_browser():
    """Waits for the server to spin up, then opens the browser."""
    webbrowser.open("http://localhost:8501")

if __name__ == "__main__":
    # 1. Handle PyInstaller's temporary directory pathing
    if getattr(sys, 'frozen', False):
        application_path = sys._MEIPASS
        os.chdir(application_path)
        
    print("===================================================")
    print(" OST STUDIO LAUNCHER ")
    print("===================================================")
    print(" 1. Generate Security Keys")
    print(" 2. Launch OST Studio")
    print("===================================================")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == '1':
        # Import and run the keygen from the new core/studio folder
        from core.studio import keys
        keys.run()
        input("\nPress Enter to exit...")
        sys.exit(0)
        
    elif choice == '2':
        # Tell Streamlit to run the studio.py file headlessly
        sys.argv = ["streamlit", "run", "core/studio/studio.py", "--server.headless=true", "--global.developmentMode=false"]
        
        # Schedule the browser to open
        Timer(2.5, open_browser).start()
        
        print("\n===================================================")
        print(" OST STUDIO IS RUNNING ")
        print(" DO NOT CLOSE THIS WINDOW. ")
        print("===================================================")
        
        # Boot the Streamlit server
        sys.exit(stcli.main())
        
    else:
        print("\nInvalid choice. Exiting...")
        sys.exit(1)