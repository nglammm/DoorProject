import os
import sys
import argparse
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path

# Configuration
SAMPLE_RATE = 16000
DURATION = 5  # Seconds per sample
NUM_SAMPLES = 3
PROFILES_DIR = Path("enrolled_voices")

def record_sample(sample_num, total_samples):
    print(f"\n[{sample_num}/{total_samples}] Prepare to speak for {DURATION} seconds...")
    sd.sleep(1000)
    print(">>> SPEAK NOW (Read a sentence naturally) <<<")
    
    # Record mono audio at 16kHz
    recording = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
    sd.wait()
    print("Done recording sample.")
    return np.squeeze(recording)

def enroll_user(username):
    PROFILES_DIR.mkdir(exist_ok=True)
    
    print("Loading Voice Encoder model...")
    encoder = VoiceEncoder()
    
    embeddings = []
    for i in range(1, NUM_SAMPLES + 1):
        input(f"\nPress Enter when ready to record sample {i} of {NUM_SAMPLES}...")
        audio_data = record_sample(i, NUM_SAMPLES)
        
        # Preprocess audio (trims silence, normalizes volume)
        wav = preprocess_wav(audio_data, source_sr=SAMPLE_RATE)
        
        if len(wav) < SAMPLE_RATE * 1.5:
            print("Warning: Audio too short or quiet. Try speaking louder next time.")
            
        # Compute 256-D speaker embedding
        embed = encoder.embed_utterance(wav)
        embeddings.append(embed)

    # Average the embeddings and normalize to unit length
    mean_embedding = np.mean(embeddings, axis=0)
    mean_embedding = mean_embedding / np.linalg.norm(mean_embedding)

    # Save voice profile to disk
    profile_path = PROFILES_DIR / f"{username.lower()}.npy"
    np.save(profile_path, mean_embedding)
    print(f"\nSuccess! Voice profile for '{username}' saved to {profile_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enroll a user's voice offline.")
    parser.add_argument("name", type=str, help="Name of the person to enroll (e.g., alice)")
    args = parser.parse_args()
    
    try:
        enroll_user(args.name)
    except KeyboardInterrupt:
        print("\nEnrollment cancelled.")
        sys.exit(0)