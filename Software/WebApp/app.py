from flask import Flask, render_template, request, jsonify
import serial
import serial.tools.list_ports
import threading
import time
from datetime import datetime

app = Flask(__name__)


## Inicjalizacja połączenia UART

def find_esp32_port():
    """Funkcja do automatycznego znajdowania portu ESP32"""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'USB' in port.description or 'Serial' in port.description or 'ESP32' in port.description:
            try:
                # Próba otwarcia portu do testu
                test_ser = serial.Serial(port.device, 115200, timeout=1)
                test_ser.write(b'\xA5\x20\x00\x5A')  # Komenda GET_TELEMETRY
                response = test_ser.read(6)  # Odczyt nagłówka odpowiedzi
                test_ser.close()
                if len(response) >= 6 and response[0] == 0xA5 and response[-1] == 0x5A:
                    return port.device
            except:
                continue
    return None


# Próba inicjalizacji prawdziwego połączenia UART
ser = None
try:
    uart_port = find_esp32_port()
    if uart_port:
        ser = serial.Serial(uart_port, 115200, timeout=1)
        print(f"Połączono z ESP32 na porcie {uart_port}")
    else:
        print("Nie znaleziono ESP32. Uruchamiam w trybie symulacji.")
except Exception as e:
    print(f"Błąd inicjalizacji UART: {str(e)}. Uruchamiam w trybie symulacji.")

## Globalne zmienne stanu

system_status = {
    'frequency': 5000,
    'modulation': 'SPWM',
    'output_voltage': 0,
    'output_current': 0,
    'temperature': 25,
    'is_running': False,
    'error': None,
    'last_update': datetime.now().isoformat(),
    'uart_connected': ser is not None
}

## Funkcje komunikacji UART

def calculate_checksum(data):
    """Obliczanie sumy kontrolnej XOR"""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def send_uart_command(command, data=None):
    """
    Wysyłanie komendy do ESP32 przez UART
    Format ramki: [0xA5, command, length, data..., checksum, 0x5A]
    """
    # Symulacja jeśli nie ma połączenia UART
    if ser is None:
        print(f"Symulacja: Wysłano komendę {command}, dane: {data}")
        # Aktualizacja stanu lokalnie dla symulacji
        if command == 'SET_FREQ':
            system_status['frequency'] = data
        elif command == 'START':
            system_status['is_running'] = True
        elif command == 'STOP':
            system_status['is_running'] = False
        elif command == 'SET_MOD':
            system_status['modulation'] = 'SPWM' if data == 0 else 'SVPWM'
        return True

    try:
        data_bytes = []
        if data is not None:
            if command == 'SET_FREQ':
                data_bytes = [(data >> 8) & 0xFF, data & 0xFF]
            elif command == 'SET_MOD':
                data_bytes = [data]

        cmd_byte = {
            'SET_FREQ': 0x01,
            'SET_MOD': 0x02,
            'START': 0x10,
            'STOP': 0x11,
            'GET_TELEMETRY': 0x20
        }.get(command, 0x00)

        frame = bytearray()
        frame.append(0xA5)  # Start byte
        frame.append(cmd_byte)  # Command
        frame.append(len(data_bytes))  # Length
        frame.extend(data_bytes)  # Data

        checksum = calculate_checksum(frame)
        frame.append(checksum)

        frame.append(0x5A)  # Stop byte

        ser.write(frame)
        return True

    except Exception as e:
        print(f"Błąd wysyłania komendy UART: {str(e)}")
        system_status['error'] = f"Błąd komunikacji: {str(e)}"
        return False


def read_uart_response():
    """Odczyt odpowiedzi z UART"""
    if ser is None:
        return None

    try:
        if ser.in_waiting >= 6:
            start_byte = ser.read(1)[0]
            if start_byte != 0xA5:
                return None

            header = ser.read(2)  # Command i Length
            length = header[1]
            data = ser.read(length + 2)  # Data + Checksum + Stop

            if data[-1] != 0x5A:
                return None

            full_frame = bytes([start_byte]) + header + data
            checksum = calculate_checksum(full_frame[:-2])
            if checksum != full_frame[-2]:
                return None

            return {
                'command': header[0],
                'length': length,
                'data': data[:-2],
                'timestamp': datetime.now().isoformat()
            }

    except Exception as e:
        print(f"Błąd odczytu UART: {str(e)}")
        system_status['error'] = f"Błąd odczytu: {str(e)}"

    return None


def process_uart_responses():
    """Przetwarzanie odpowiedzi od ESP32 w tle"""
    while True:
        response = read_uart_response()
        if response:
            # Aktualizacja statusu na podstawie odpowiedzi
            if response['command'] == 0x20:  # Telemetria
                if response['length'] == 12:
                    system_status['frequency'] = int.from_bytes(response['data'][0:2], 'big')
                    system_status['output_voltage'] = int.from_bytes(response['data'][4:6], 'big') / 10.0
                    system_status['output_current'] = int.from_bytes(response['data'][8:10], 'big') / 10.0
                    system_status['temperature'] = int.from_bytes(response['data'][10:12], 'big') / 10.0
                    system_status['last_update'] = datetime.now().isoformat()

        time.sleep(0.1)


## Wątek odczytu UART

if ser is not None:
    uart_thread = threading.Thread(target=process_uart_responses)
    uart_thread.daemon = True
    uart_thread.start()
else:
    # Symulacja danych jeśli brak UART
    def simulate_uart_communication():
        while True:
            if system_status['is_running']:
                system_status['output_voltage'] = 48 * 0.8
                system_status['output_current'] = 2.5
                system_status['temperature'] = 45 + (system_status['frequency'] / 1000)
            else:
                system_status['output_voltage'] = 0
                system_status['output_current'] = 0
                system_status['temperature'] = 25
            system_status['last_update'] = datetime.now().isoformat()
            time.sleep(1)


    sim_thread = threading.Thread(target=simulate_uart_communication)
    sim_thread.daemon = True
    sim_thread.start()


## Endpointy Flask

@app.route('/')
def index():
    return render_template('index.html', status=system_status)


@app.route('/api/start', methods=['POST'])
def start_inverter():
    success = send_uart_command('START')
    if success:
        return jsonify({'status': 'success', 'message': 'Falownik uruchomiony'})
    return jsonify({'status': 'error', 'message': 'Błąd komunikacji z falownikiem'}), 500


@app.route('/api/stop', methods=['POST'])
def stop_inverter():
    success = send_uart_command('STOP')
    if success:
        return jsonify({'status': 'success', 'message': 'Falownik zatrzymany'})
    return jsonify({'status': 'error', 'message': 'Błąd komunikacji z falownikiem'}), 500


@app.route('/api/set_frequency', methods=['POST'])
def set_frequency():
    freq = request.json.get('frequency')
    if 1000 <= freq <= 20000:
        success = send_uart_command('SET_FREQ', freq)
        if success:
            return jsonify({'status': 'success', 'message': f'Ustawiono częstotliwość: {freq} Hz'})
        return jsonify({'status': 'error', 'message': 'Błąd komunikacji z falownikiem'}), 500
    return jsonify({'status': 'error', 'message': 'Nieprawidłowa częstotliwość'}), 400


@app.route('/api/set_modulation', methods=['POST'])
def set_modulation():
    mod_type = request.json.get('mod_type')
    if mod_type in [0, 1]:
        success = send_uart_command('SET_MOD', mod_type)
        if success:
            return jsonify({'status': 'success', 'message': 'Zmieniono typ modulacji'})
        return jsonify({'status': 'error', 'message': 'Błąd komunikacji z falownikiem'}), 500
    return jsonify({'status': 'error', 'message': 'Nieprawidłowy typ modulacji'}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    # Wysłanie żądania aktualizacji telemetrii
    if ser is not None:
        send_uart_command('GET_TELEMETRY')
    return jsonify(system_status)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)