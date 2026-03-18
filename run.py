#!/usr/bin/env python3
"""
run.py – Menu to start app.py or refresh_tokens.py
"""

import os
import sys
import subprocess
import time

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_menu():
    clear_screen()
    print("=" * 50)
    print("        FREE FIRE BOT CONTROL MENU")
    print("=" * 50)
    print("1) Start Flask app (app.py)")
    print("2) Refresh tokens (refresh_tokens.py)")
    print("0) Exit")
    print("=" * 50)

def run_script(script_name):
    """Run a Python script in the foreground."""
    print(f"\n🚀 Starting {script_name} ...\n")
    try:
        # Use the same Python interpreter
        subprocess.run([sys.executable, script_name])
    except KeyboardInterrupt:
        print(f"\n⏹️  {script_name} interrupted.")
    except Exception as e:
        print(f"\n❌ Error running {script_name}: {e}")
    input("\nPress Enter to return to menu...")

def main():
    while True:
        print_menu()
        choice = input("Choose an option: ").strip()

        if choice == "1":
            run_script("app.py")
        elif choice == "2":
            run_script("refresh_tokens.py")
        elif choice == "0":
            print("Goodbye!")
            sys.exit(0)
        else:
            print("Invalid option. Press Enter to continue...")
            input()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)