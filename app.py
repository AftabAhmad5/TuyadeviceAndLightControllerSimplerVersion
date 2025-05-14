from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import requests
import tinytuya
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Weather API setup
WEATHER_API_KEY = '80929de7dd9a4b60b28195216251205'
WEATHER_LOCATION = 'London'

# Initialize database
def init_db():
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  device_name TEXT,
                  device_id TEXT UNIQUE,
                  local_key TEXT,
                  device_type TEXT,
                  config TEXT,
                  device_ip TEXT,
                  power_state INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# Get weather data from WeatherAPI
def get_weather_data(location):
    url = f'https://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days=1'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {
            'location': data.get('location', {}).get('name', 'N/A'),
            'date': data.get('location', {}).get('localtime', 'N/A').split()[0],
            'temperature': data.get('current', {}).get('temp_c', 'N/A'),
            'condition': data.get('current', {}).get('condition', {}).get('text', 'N/A'),
            'humidity': data.get('current', {}).get('humidity', 'N/A'),
            'wind_speed': data.get('current', {}).get('wind_mph', 'N/A'),
            'feels_like': data.get('current', {}).get('feelslike_c', 'N/A'),
            'uv_index': data.get('current', {}).get('uv', 'N/A'),
            'sunrise': data.get('forecast', {}).get('forecastday', [{}])[0].get('astro', {}).get('sunrise', 'N/A'),
            'sunset': data.get('forecast', {}).get('forecastday', [{}])[0].get('astro', {}).get('sunset', 'N/A')
        }
    except requests.exceptions.RequestException as e:
        print(f"Weather API request failed: {e}")
        return {
            'location': 'N/A',
            'date': 'N/A',
            'temperature': 'N/A',
            'condition': 'N/A',
            'humidity': 'N/A',
            'wind_speed': 'N/A',
            'feels_like': 'N/A',
            'uv_index': 'N/A',
            'sunrise': 'N/A',
            'sunset': 'N/A'
        }
    except Exception as e:
        print(f"Weather API error: {e}")
        return {
            'location': 'N/A',
            'date': 'N/A',
            'temperature': 'N/A',
            'condition': 'N/A',
            'humidity': 'N/A',
            'wind_speed': 'N/A',
            'feels_like': 'N/A',
            'uv_index': 'N/A',
            'sunrise': 'N/A',
            'sunset': 'N/A'
        }

# Get temperature from Tuya thermostat
def get_temperature_from_tuya():
    try:
        # Replace with your actual Tuya device ID for the temperature sensor
        device_id = "your_thermostat_device_id"  
        response = tinytuya.get_device_status(device_id)
        temperature_status = next((item for item in response.get('dps', []) if item['code'] == 'temp_current'), None)
        return temperature_status.get('value', 24) if temperature_status else 24
    except:
        return 24  # Fallback value

@app.route('/temperature')
def temperature():
    temp = get_temperature_from_tuya()
    return jsonify({'temperature': temp})

@app.route('/')
def dashboard():
    weather_data = get_weather_data(WEATHER_LOCATION)
    paired_devices = get_paired_devices()
    
    # Get room temperature
    room_temperature = get_temperature_from_tuya()
    
    # Get weather data for other cities
    other_cities = ['New York', 'Tokyo', 'Sydney', 'Paris']
    city_weather = {}
    for city in other_cities:
        city_weather[city] = get_weather_data(city)
    
    return render_template('dashboard.html', 
                          weather=weather_data,
                          paired_devices=paired_devices,
                          room_temperature=room_temperature,
                          city_weather=city_weather)

@app.route('/show_add_device_form')
def show_add_device_form():
    return render_template('add_device.html')

@app.route('/add_device', methods=['POST'])
def add_device():
    device_name = request.form['device_name']
    device_id = request.form['device_id']
    local_key = request.form['local_key']
    device_ip = request.form['device_ip']
    device_type = request.form['device_type']
    config = request.form['config']
    
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO devices (device_name, device_id, local_key, device_type, config, device_ip) VALUES (?, ?, ?, ?, ?, ?)",
                 (device_name, device_id, local_key, device_type, config, device_ip))
        conn.commit()
        return redirect(url_for('dashboard'))
    except sqlite3.IntegrityError:
        return "Device already exists!"
    finally:
        conn.close()

@app.route('/delete_device/<device_id>')
def delete_device(device_id):
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/toggle_power/<device_id>', methods=['POST'])
def toggle_power(device_id):
    power_state = request.json.get('powerState', False)
    
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("UPDATE devices SET power_state = ? WHERE device_id = ?", (1 if power_state else 0, device_id))
    conn.commit()
    conn.close()
    
    control_tuya_device(device_id, power_state)
    
    return jsonify({'success': True, 'powerState': power_state})

def control_tuya_device(device_id, power_state):
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("SELECT device_ip, local_key FROM devices WHERE device_id = ?", (device_id,))
    device = c.fetchone()
    conn.close()
    
    if device:
        device_ip, local_key = device
        device = tinytuya.Device(device_id, device_ip, local_key)
        device.set_version(3.1)
        
        if power_state:
            payload = device.generate_payload('set', {'1': True})
        else:
            payload = device.generate_payload('set', {'1': False})
            
        response = device._send_receive(payload)
        return response
    
    return None

def get_paired_devices():
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("SELECT * FROM devices")
    return c.fetchall()

if __name__ == '__main__':
    app.run(debug=True)