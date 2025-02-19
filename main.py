import openai
import speech_recognition as sr
import time
import os
import subprocess
import struct
import logging
import pyaudio
import pvporcupine  
import requests
import math
import threading
import re
#EXPORT YOUR OPENWEATHER, OPENAI, PORCUPINE, AND NEWSAPI API KEYS
openai_api_key = os.getenv("OPENAI_API_KEY")
newsapi_key = os.getenv("NEWSAPI_KEY")
porcupine_api_key = os.getenv("PVC_ACCESS_KEY")
openweather_api_key = os.getenv("OPENWEATHER_API_KEY")

# Logging settings
logging.getLogger('speech_recognition').setLevel(logging.CRITICAL)

# Global variables
stop_speech_flag = False
conversation_history = []
speech_process = None 

# Path to your Porcupine keyword model file!!!
keyword_model_path = "Hey_Rust/Hey-Rust_en_linux_v3_0_0/Hey-Rust_en_linux_v3_0_0.ppn"

# Initialize Porcupine with API key and keyword file
porcupine = pvporcupine.create(
    access_key=porcupine_api_key,
    keyword_paths=[keyword_model_path]  
)

print("Porcupine initialized successfully!")

# Initialize pyaudio
pa = pyaudio.PyAudio()
audio_stream = pa.open(
    rate=porcupine.sample_rate, channels=1, format=pyaudio.paInt16, 
    input=True, frames_per_buffer=porcupine.frame_length
)

# Helper functions
def listen_for_stop():
    global stop_speech_flag
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    while True:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source, phrase_time_limit=2)

        try:
            text = recognizer.recognize_google(audio).lower()
            print(f"You said: {text}")
            if "stop" in text:
                stop_speech_flag = True
                print("Stopping speech...")
        except sr.UnknownValueError:
            pass
        except sr.RequestError:
            pass

def speak(text):
    global stop_speech_flag, speech_process
    stop_speech_flag = False  

    safe_text = text.replace("'", "'\\''")
    speech_process = subprocess.Popen(f"echo '{safe_text}' | festival --tts", shell=True, preexec_fn=os.setsid)

    while speech_process.poll() is None:
        if stop_speech_flag:
            os.killpg(os.getpgid(speech_process.pid), 9)  
            print("Speech stopped!")
            return
        time.sleep(0.1)  

def wait_for_wake_word():
    print("Listening for wake word...")
    while True:
        pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
        pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)
        if porcupine.process(pcm) >= 0:
            print("Wake word detected!")
            return  

def listen():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    print("Please say something...")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)

    try:
        text = recognizer.recognize_google(audio)
        print(f"You said: {text}")
        return text
    except sr.UnknownValueError:
        speak("Sorry, I did not understand that. Could you repeat?")
        return None
    except sr.RequestError:
        speak("Could not request results from Google Speech Recognition service.")
        return None

def get_gpt_response(user_input):
    try:
        conversation_history.append({"role": "user", "content": user_input})
        response = openai.ChatCompletion.create(
            model="gpt-4", messages=conversation_history, temperature=0.7, max_tokens=200
        )
        gpt_response = response['choices'][0]['message']['content'].strip()
        conversation_history.append({"role": "assistant", "content": gpt_response})
        if len(conversation_history) > 10:
            conversation_history.pop(0)
        return gpt_response
    except openai.error.RateLimitError:
        print("Rate limit exceeded. Please try again later.")
        time.sleep(60)
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_news(query="latest news"):
    url = f'https://newsapi.org/v2/everything?q={query}&apiKey={newsapi_key}&pageSize=3'
    try:
        response = requests.get(url)
        data = response.json()
        if data["status"] == "ok" and data["totalResults"] > 0:
            articles = data["articles"][:3]
            return "\n".join([f"Article {i+1}: {a['title']}. {a['description']}. More info: {a['url']}." for i, a in enumerate(articles)])
        return "No news found at the moment."
    except Exception as e:
        return f"An error occurred: {e}"

def fahrenheit(x):
    return math.floor(x * 1.8 + 32)

def get_weather(location="Brookhaven, Georgia"):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    complete_url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    
    try:
        response = requests.get(complete_url)
        data = response.json()
        if "main" not in data:
            return f"Unable to retrieve weather data for {location}. Please try again."
        
        temp = fahrenheit(data["main"]["temp"])
        description = data["weather"][0]["description"]
        return f"The current temperature in {location} is {temp}°F with {description}."
    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"

def extract_location(user_input):
    match = re.search(r"weather in ([\w\s]+)", user_input.lower())
    return match.group(1).strip() if match else "Brookhaven, Georgia"

# Main chatbot function
def main():
    global stop_speech_flag  
    print("Chatbot is ready! Say 'Hey Rusty' to activate.")

    stop_thread = threading.Thread(target=listen_for_stop, daemon=True)
    stop_thread.start()

    while True:
        try:
            wait_for_wake_word()
            user_input = listen()

            if user_input:
                if "stop" in user_input.lower():
                    print("Stopping speech...")
                    stop_speech_flag = True
                    speak("Okay, stopping.")  
                    time.sleep(1)
                    stop_speech_flag = False  
                    continue  

                if "news" in user_input.lower():
                    print("Fetching news...")
                    news_report = get_news(user_input)
                    print(f"News report: {news_report}")
                    speak(news_report)

                elif "weather" in user_input.lower():
                    location = extract_location(user_input)
                    weather_report = get_weather(location)
                    print(f"Weather report: {weather_report}")
                    speak(weather_report)

                else:
                    gpt_response = get_gpt_response(user_input)
                    print(f"Rusty McDingdong: {gpt_response}")
                    speak(gpt_response)

        except Exception as e:
            print(f"Error in main loop: {e}")

        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        if porcupine:
            porcupine.delete()
        if audio_stream:
            audio_stream.close()
        if pa:
            pa.terminate()
