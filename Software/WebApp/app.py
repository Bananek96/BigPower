from flask import Flask, render_template, request, jsonify
import serial
import threading
import time

app = Flask(__name__)

# Symulacja połączenia UART (w rzeczywistości podłącz do odpowiedniego portu)
# ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)

# Globalne zmienne stanu
system_status = {
    'frequency': 5000,
    'modulation': 'SPWM',
    'output_voltage': 0,
    'output_current': 0,
    'temperature': 25,
    'is_running': False,
    'error': None
}


def simulate_uart_communication():
    """Symulacja odbierania danych z falownika"""
    while True:
        # W rzeczywistości odbierz dane z UART
        # data = ser.read()
        # process_incoming_data(data)
        time.sleep(1)
        # Symulacja odczytu parametrów
        if system_status['is_running']:
            system_status['output_voltage'] = 48 * 0.8
            system_status['output_current'] = 2.5
            system_status['temperature'] = 45 + (system_status['frequency'] / 1000)
        else:
            system_status['output_voltage'] = 0
            system_status['output_current'] = 0
            system_status['temperature'] = 25


# Uruchom wątek symulacji komunikacji
thread = threading.Thread(target=simulate_uart_communication)
thread.daemon = True
thread.start()


def send_uart_command(command, data=None):
    """Funkcja do wysyłania komend do STM32 przez UART"""
    # W rzeczywistości:
    # frame = create_uart_frame(command, data)
    # ser.write(frame)
    print(f"Wysłano komendę: {command}, dane: {data}")

    # Aktualizacja stanu lokalnie dla symulacji
    if command == 'SET_FREQ':
        system_status['frequency'] = data
    elif command == 'START':
        system_status['is_running'] = True
    elif command == 'STOP':
        system_status['is_running'] = False
    elif command == 'SET_MOD':
        system_status['modulation'] = 'SPWM' if data == 0 else 'SVPWM'


@app.route('/')
def index():
    return render_template('index.html', status=system_status)


@app.route('/api/start', methods=['POST'])
def start_inverter():
    send_uart_command('START')
    return jsonify({'status': 'success', 'message': 'Falownik uruchomiony'})


@app.route('/api/stop', methods=['POST'])
def stop_inverter():
    send_uart_command('STOP')
    return jsonify({'status': 'success', 'message': 'Falownik zatrzymany'})


@app.route('/api/set_frequency', methods=['POST'])
def set_frequency():
    freq = request.json.get('frequency')
    if 1000 <= freq <= 20000:
        send_uart_command('SET_FREQ', freq)
        return jsonify({'status': 'success', 'message': f'Ustawiono częstotliwość: {freq} Hz'})
    return jsonify({'status': 'error', 'message': 'Nieprawidłowa częstotliwość'}), 400


@app.route('/api/set_modulation', methods=['POST'])
def set_modulation():
    mod_type = request.json.get('mod_type')
    if mod_type in [0, 1]:
        send_uart_command('SET_MOD', mod_type)
        return jsonify({'status': 'success', 'message': 'Zmieniono typ modulacji'})
    return jsonify({'status': 'error', 'message': 'Nieprawidłowy typ modulacji'}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(system_status)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)