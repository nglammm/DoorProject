import os
import sys
import json
import queue
import numpy as np
import sounddevice as sd
from pathlib import Path
from vosk import Model, KaldiRecognizer, SetLogLevel
from resemblyzer import VoiceEncoder, preprocess_wav

# Configuration
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000  # 0.25 seconds per audio block
SIMILARITY_THRESHOLD = 0.76  # Adjust between 0.70 (lenient) and 0.82 (strict)
PROFILES_DIR = Path("enrolled_voices")
VOSK_MODEL_PATH = "model"

# Suppress verbose Vosk logs
SetLogLevel(-1)

audio_queue = queue.Queue()

def load_enrolled_voices():
    if not PROFILES_DIR.exists():
        print(f"Error: '{PROFILES_DIR}' directory not found. Run enroll_voice.py first.")
        sys.exit(1)
        
    profiles = {}
    for file in PROFILES_DIR.glob("*.npy"):
        name = file.stem
        profiles[name] = np.load(file)
        
    if not profiles:
        print("Error: No voice profiles found! Enroll a voice first with enroll_voice.py.")
        sys.exit(1)
        
    print(f"Loaded {len(profiles)} voice profile(s): {', '.join(profiles.keys())}")
    return profiles

def identify_speaker(encoder, audio_int16, profiles):
    # Convert int16 PCM buffer to float32 in range [-1.0, 1.0]
    audio_float32 = audio_int16.astype(np.float32) / 32768.0
    
    # Preprocess and check if enough speech exists for reliable ID
    wav = preprocess_wav(audio_float32, source_sr=SAMPLE_RATE)
    if len(wav) < SAMPLE_RATE * 0.8:  # Less than 0.8s of active speech
        return "Too Short to ID", 0.0

    # Extract speaker embedding
    utterance_embed = encoder.embed_utterance(wav)
    
    # Compute cosine similarity against enrolled profiles
    best_speaker = "Unknown"
    best_score = -1.0
    
    for name, profile_embed in profiles.items():
        score = float(np.dot(utterance_embed, profile_embed))
        if score > best_score:
            best_score = score
            best_speaker = name

    if best_score >= SIMILARITY_THRESHOLD:
        return best_speaker.capitalize(), best_score
    else:
        return "Unknown", best_score

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))

def main():
    profiles = load_enrolled_voices()
    
    if not os.path.exists(VOSK_MODEL_PATH):
        print(f"Error: Vosk model folder '{VOSK_MODEL_PATH}' not found.")
        sys.exit(1)

    print("Loading models into memory...")
    encoder = VoiceEncoder()
    vosk_model = Model(VOSK_MODEL_PATH)
    recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE)

    # Buffer to accumulate raw audio bytes for the current phrase
    current_phrase_pcm = bytearray()

    print("\n--- Listening (Press Ctrl+C to stop) ---")
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype='int16',
                           channels=1, callback=audio_callback):
        while True:
            data = audio_queue.get()
            current_phrase_pcm.extend(data)

            # AcceptWaveform returns True when a silence boundary follows speech
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()

                if text:
                    # Convert accumulated phrase bytes to numpy int16 array
                    audio_np = np.frombuffer(current_phrase_pcm, dtype=np.int16)
                    speaker, confidence = identify_speaker(encoder, audio_np, profiles)
                    
                    print(f"[{speaker} ({confidence:.2f})]: {text}")

                # Clear buffer for the next spoken phrase
                current_phrase_pcm.clear()
            else:
                # Prevent unbounded memory growth during long silence
                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                if not partial and len(current_phrase_pcm) > SAMPLE_RATE * 2 * 3:
                    # Keep only the last 1 second of pre-roll silence
                    current_phrase_pcm = current_phrase_pcm[-(SAMPLE_RATE * 2):]

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)