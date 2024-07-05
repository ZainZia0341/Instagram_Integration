import os
import json
import requests
import subprocess
import openai
from google.cloud import texttospeech

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INSTA_USER_ID = os.getenv("Insta_User_ID")
openai.api_key = OPENAI_API_KEY
tts_client = texttospeech.TextToSpeechClient()

def InstaHandler(event, context):
    http_method = event.get('httpMethod')
    if http_method == 'GET':
        return verify_token(event)
    elif http_method == 'POST':
        return webhook_event(event)
    else:
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }

def verify_token(event):
    params = event.get('queryStringParameters')
    if params.get('hub.verify_token') == VERIFY_TOKEN:
        return {
            'statusCode': 200,
            'body': params.get('hub.challenge')
        }
    return {
        'statusCode': 403,
        'body': 'Error, wrong validation token'
    }

def webhook_event(event):
    body = json.loads(event.get('body'))
    for entry in body['entry']:
        if 'changes' in entry:
            for change in entry['changes']:
                if change['field'] == 'stories':
                    story_id = change['value']['story_id']
                    download_story(story_id)
    return {
        'statusCode': 200,
        'body': json.dumps({'success': True})
    }

def download_story(story_id):
    url = f"https://graph.instagram.com/{story_id}?fields=id,media_type,media_url&access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        story_data = response.json()
        if story_data['media_type'] == 'VIDEO':
            video_url = story_data['media_url']
            response = requests.get(video_url, stream=True)
            if response.status_code == 200:
                with open('/tmp/input_video.mp4', 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                process_video('/tmp/input_video.mp4')
            else:
                print("Failed to download video")
        else:
            print("Unsupported media type")

def process_video(video_path):
    subprocess.call(['ffmpeg', '-i', video_path, '-q:a', '0', '-map', 'a', '/tmp/audio.wav'])
    transcript = transcribe_audio('/tmp/audio.wav')
    translated_text = translate_text(transcript, 'English')
    generate_audio(translated_text, '/tmp/output_audio.mp3')
    replace_audio(video_path, '/tmp/output_audio.mp3', '/tmp/output_video.mp4')
    repost_instagram_video('/tmp/output_video.mp4', ACCESS_TOKEN, INSTA_USER_ID)

def transcribe_audio(audio_path):
    with open(audio_path, "rb") as audio_file:
        transcription_response = openai.Audio.transcribe("whisper-1", file=audio_file)
    return transcription_response['text']

def translate_text(text, target_language):
    response = openai.Completion.create(
        engine="davinci",
        prompt=f"Translate the following text to {target_language} and remove any slang or inappropriate language:\n\n{text}",
        max_tokens=1000
    )
    return response.choices[0].text.strip()

def generate_audio(text, output_path, language_code='en-US'):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=language_code, ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    with open(output_path, 'wb') as out:
        out.write(response.audio_content)

def replace_audio(video_path, audio_path, output_path):
    subprocess.call(['ffmpeg', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_path])

def repost_instagram_video(video_path, access_token, user_id):
    video_url = f"https://graph-video.instagram.com/v11.0/{user_id}/media"
    data = {
        'access_token': access_token,
        'media_type': 'VIDEO',
        'video_url': video_path,
        'caption': 'Translated Video'
    }
    response = requests.post(video_url, data=data)
    return response.json()
