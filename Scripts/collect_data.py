import serial
import time
import csv

def collect_from_arduino(port='/dev/ttyUSB0', baudrate=9600, output_file='data/raw/arduino_data.csv'):
    ser = serial.Serial(port, baudrate)
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['timestamp', 'voltage', 'current_draw'])  # Add your sensor headers
        while True:  # Run for a fixed time or until interrupt
            line = ser.readline().decode('utf-8').strip()
            if line:
                data = [time.time()] + line.split(',')
                writer.writerow(data)
            time.sleep(0.01)  # 100Hz sampling

# Example: collect_from_arduino()