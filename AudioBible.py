import csv
import os
import ffmpeg
from pathlib import Path
from mutagen.id3 import ID3, TIT2, COMM, TPE1, TPUB, TYER, TLAN, TRCK, TALB, TCOP

import Media
import Services
from Asset import BUILD_FOLDER

ROOT = Path(__file__).resolve().parent
INSTALLED = ROOT == Path("/usr/share/scripturesstudio")

if INSTALLED:
	SOURCE_AUDIO_FOLDER = Path("/usr/share/audiobible/source")
	ORIGINAL_AUDIO_FOLDER = Path("/usr/share/audiobible/shmueloff")
	CLONED_AUDIO_FOLDER = Path("/usr/share/audiobible/shmueloff-darkknox2")
	ENGLISH_AUDIO_FOLDER = Path("/usr/share/audiobible/english")
	TITLES_AUDIO_FOLDER = Path("/var/lib/audiobible/titles")
	ORIGINAL_CSV_FOLDER = Path("/var/lib/audiobible/original")
	CLONED_CSV_FOLDER = Path("/var/lib/audiobible/cloned")
	ENGLISH_CSV_FOLDER = Path("/var/lib/audiobible/english")
else:
	SOURCE_AUDIO_FOLDER = ROOT / "audio" / "shmueloff-source"
	ORIGINAL_AUDIO_FOLDER = ROOT / "audio" / "shmueloff-original"
	CLONED_AUDIO_FOLDER = ROOT / "audio" / "shmueloff-darkknox2"
	ENGLISH_AUDIO_FOLDER = ROOT / "audio" / "darkknox2-english"
	TITLES_AUDIO_FOLDER = ROOT / "audio" / "titles"
	ORIGINAL_CSV_FOLDER = ORIGINAL_AUDIO_FOLDER
	CLONED_CSV_FOLDER = CLONED_AUDIO_FOLDER
	ENGLISH_CSV_FOLDER = ENGLISH_AUDIO_FOLDER

TITLES_CSV = TITLES_AUDIO_FOLDER / "titles.csv"
ORIGINAL_CSV = ORIGINAL_CSV_FOLDER / "original.csv"
CLONED_CSV = CLONED_CSV_FOLDER / "cloned.csv"
ENGLISH_CSV = ENGLISH_CSV_FOLDER / "english.csv"
ALIGNMENT_CSV = CLONED_CSV_FOLDER / "alignment.csv"

class AudioBible:
	_instance = None

	@classmethod
	def get_instance(cls):
		if cls._instance is None:
			cls._instance = AudioBible()
		return cls._instance

	def __init__(self):
		self.title_durations = {}
		self.cloned_durations = {}
		self.english_durations = {}
		self.timings = {}
		self.alignment = {}
		self._load_timings()
		self.load_cloned_durations()
		self.load_alignment()
		with open(TITLES_CSV, 'r', encoding='utf-8') as f:
			reader = csv.DictReader(f)
			for row in reader:
				self.title_durations[row['filename']] = float(row['duration'])

	def title_duration(self, filename):
		return self.title_durations.get(filename)

	def _load_timings(self):
		with open(ORIGINAL_CSV, 'r', encoding='utf-8') as file:
			reader = csv.DictReader(file)
			for row in reader:
				book_number = int(row['book'])
				chapter_number = int(row['chapter'])
				verse_number = int(row['verse'])
				start_time = float(row['start'])
				end_time = float(row['end'])
				key = (book_number, chapter_number, verse_number)
				self.timings[key] = (start_time, end_time)
	
	def get_timing(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return self.timings.get(key, (0.0, 0.0))

	def set_timing(self, verse, start_time, end_time):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		self.timings[key] = (start_time, end_time)
		self.save_timings()
		#export_original_mp3(book_num, chapter_num, verse_num)
		
	def save_timings(self):
		with open(ORIGINAL_CSV, 'w', newline='', encoding='utf-8') as file:
			writer = csv.writer(file)
			writer.writerow(['book', 'chapter', 'verse', 'start', 'end'])
			for (book_num, chapter_num, verse_num), (start_time, end_time) in sorted(self.timings.items()):
				writer.writerow([book_num, chapter_num, verse_num, start_time, end_time])


	def load_cloned_durations(self):
		used_durations = set()
		with open(CLONED_CSV, 'r', encoding='utf-8') as file:
			reader = csv.DictReader(file)
			for row in reader:
				book_number = int(row['book'])
				chapter_number = int(row['chapter'])
				verse_number = int(row['verse'])
				duration = float(row['duration'])
				while duration in used_durations:
					duration -= 0.000001
				used_durations.add(duration)
				key = (book_number, chapter_number, verse_number)
				self.cloned_durations[key] = duration

	def load_alignment(self):
		with open(ALIGNMENT_CSV, 'r', encoding='utf-8') as file:
			for row in csv.DictReader(file):
				key = (int(row['book']), int(row['chapter']), int(row['verse']))
				self.alignment.setdefault(key, {})[int(row['word'])] = (float(row['start']), float(row['end']))

	def word_timings(self, verse):
		# {word number: (start, end)} in seconds from the start of the cloned verse audio
		return self.alignment[(verse.chapter.book.number, verse.chapter.number, verse.number)]

	def load_english_durations(self):
		used_durations = set()
		with open(ENGLISH_CSV, 'r', encoding='utf-8') as file:
			reader = csv.DictReader(file)
			for row in reader:
				book_number = int(row['book'])
				chapter_number = int(row['chapter'])
				verse_number = int(row['verse'])
				duration = float(row['duration'])
				while duration in used_durations:
					duration -= 0.000001
				used_durations.add(duration)
				key = (book_number, chapter_number, verse_number)
				self.english_durations[key] = duration





	def clone(self, verse):
		if not self.has_original_audio(verse):
			return False
		original_mp3_path = self.original_mp3(verse)
		cloned_mp3_path = self.cloned_mp3(verse)
		voice_id = "dPah2VEoifKnZT37774q"
		Services.speech_to_speech(original_mp3_path, voice_id, cloned_mp3_path)
		duration = Media.get_duration(cloned_mp3_path)
		self.save_cloned_duration(verse, duration)
		self.align(verse)
		return True

	def generate_english_audio(self, book, chapter, verse, english_text):
		basename = f"{book:02d}.{chapter:03d}.{verse:03d}"
		english_mp3_path = self.bible_audio.english_directory / f"{basename}.mp3"
		voice_id = "dPah2VEoifKnZT37774q"
		try:
			Services.text_to_speech(english_text, voice_id, english_mp3_path)
		except:
			return False
		duration = BibleAudio.get_audio_duration(english_mp3_path)
		self.save_english_duration(book, chapter, verse, duration)
		return True



	def align(self, verse):
		book_num = verse.chapter.book.number
		chapter_num = verse.chapter.number
		verse_num = verse.number
		cloned_mp3_path = self.cloned_mp3(verse)

		if not cloned_mp3_path.exists():
			return False

		bare_text = verse.bare_text

		word_timings = Services.word_alignment(cloned_mp3_path, bare_text)
	#	print (word_timings)
	#	exit()
	
	#	if not word_timings:
	#		return False
		
		alignment_path = Path('csv/alignment.csv')
		alignment_path.parent.mkdir(exist_ok=True)
		
		rows = []
		if alignment_path.exists():
			with open(alignment_path, 'r', encoding='utf-8') as f:
				reader = csv.DictReader(f)
				rows = [row for row in reader
				if not (int(row['book']) == book_num and
						int(row['chapter']) == chapter_num and
						int(row['verse']) == verse_num)]
		for idx, (start, end, text) in enumerate(word_timings, start=1):
			rows.append({
				'book': book_num,
				'chapter': chapter_num,
				'verse': verse_num,
				'word': idx,
				'start': f"{start:.3f}",
				'end': f"{end:.3f}"
			})

		rows.sort(key=lambda r: (int(r['book']), int(r['chapter']), int(r['verse']), int(r['word'])))
		# Write back
		with open(alignment_path, 'w', newline='', encoding='utf-8') as f:
			writer = csv.DictWriter(f, fieldnames=['book', 'chapter', 'verse', 'word', 'start', 'end'])
			writer.writeheader()
			writer.writerows(rows)
		
		return True

	def has_original_audio(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return key in self.timings
	
	def has_cloned_audio(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return key in self.cloned_durations

	def has_english_audio(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return key in self.english_durations
	

	def cloned_duration(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return self.cloned_durations.get(key, 0.0)

	def english_duration(self, verse):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		return self.english_durations.get(key, 0.0)


	def save_cloned_duration(self, verse, duration):
		self._save_duration(CLONED_CSV, verse, duration, self.cloned_durations)

	def save_english_duration(self, verse, duration):
		self._save_duration(ENGLISH_CSV, verse, duration, self.english_durations)

	def _save_duration(self, csv_path, verse, duration, durations_dict):
		key = (verse.chapter.book.number, verse.chapter.number, verse.number)
		durations_dict[key] = duration
		rows = []
		if csv_path.exists():
			with open(csv_path, 'r', encoding='utf-8') as file:
				reader = csv.DictReader(file)
				rows = list(reader)
		found = False
		for row in rows:
			if (int(row['book']) == verse.chapter.book.number and 
				int(row['chapter']) == verse.chapter.number and 
				int(row['verse']) == verse.number):
				row['duration'] = duration
				found = True
				break
		if not found:
			rows.append({
				'book': verse.chapter.book.number,
				'chapter': verse.chapter.number, 
				'verse': verse.number,
				'duration': duration
			})
		with open(csv_path, 'w', newline='', encoding='utf-8') as file:
			writer = csv.DictWriter(file, fieldnames=['book', 'chapter', 'verse', 'duration'])
			writer.writeheader()
			writer.writerows(rows)














	"""TIMESTAMPS_CSV = 'audio/timestamps.csv'
_timestamps = {}

def _load_timestamps():
	with open(TIMESTAMPS_CSV, 'r', encoding='utf-8') as file:
		reader = csv.DictReader(file)
		timestamps = {}
		for row in reader:
			book_number = int(row['book'])
			chapter_number = int(row['chapter'])
			verse_number = int(row['verse'])
			timestamp = float(row['timestamp'])
			key = (book_number, chapter_number, verse_number)
			_timestamps[key] = timestamp

def _save_timestamps():
	with open(TIMESTAMPS_CSV, 'w', newline='', encoding='utf-8') as file:
		writer = csv.writer(file)
		writer.writerow(['book', 'chapter', 'verse', 'timestamp'])
		for (book, chapter, verse), timestamp in sorted(timestamps.items()):
			writer.writerow([book, chapter, verse, timestamp])

def timestamp(book, chapter, verse):
	key = (book, chapter, verse)
	return _timestamps.get(key, 0.0)

def set_timestamp(book, chapter, verse, timestamp):
	key = (book, chapter, verse)
	_timestamps[key] = timestamp
	_save_timestamps()

_load_timestamps()
"""










	"""def export_original_mp3(self, verse):
		#print(book_num, chapter_num, verse_num)
		if not self.has_original_audio(verse):
			return
		start_time, end_time = self.get_timing(verse)
		basename = f"{verse.chapter.book.number:03d}.{verse.chapter.number:03d}.{verse.number:03d}"
			
		# First, ensure the WAV file exists by converting from source MP3 if needed
		wav = f"audio/{verse.chapter.book.number:02d}.wav"
#		source_mp3_path = sources_directory / f"{book_num:02d}.mp3"
	
#		# Convert source MP3 to WAV if WAV doesn't exist but source MP3 does
#		if not wav_path.exists() and source_mp3_path.exists():
#			(ffmpeg
#				.input(str(source_mp3_path))
#				.output(str(wav_path), acodec='pcm_s16le')
#				.overwrite_output()
#				.run()
#			)
#		if not wav_path.exists():
#			return
		out = f"cloned{basename}.mp3"
		(ffmpeg
			.input(str(wav), ss=start_time, to=end_time)
			.output(str(out), format='mp3', audio_bitrate='192k')
			.overwrite_output()
			.run()
		)"""


	"""def export_cloned_sln(self, book_num, chapter_num, verse_num):
		if not has_cloned_audio(book_num, chapter_num, verse_num):
			return False
		basename = f"{book_num:02d}.{chapter_num:03d}.{verse_num:03d}"
		cloned_mp3_path = cloned_directory / f"{basename}.mp3"
		sln_path = sln_directory / f"{basename}h.sln"
		if not cloned_mp3_path.exists():
			return False
		try:
			(ffmpeg
				.input(str(cloned_mp3_path))
				.output(str(sln_path), acodec='pcm_s16le', ar='8000', ac=1, f='s16le')
				.overwrite_output()
				.run(capture_stdout=True, capture_stderr=True, quiet=True)
			)
			return True
		except ffmpeg.Error:
			return False
	
	def export_english_sln(self, book_num, chapter_num, verse_num):
		if not has_english_audio(book_num, chapter_num, verse_num):
			return False
		basename = f"{book_num:02d}.{chapter_num:03d}.{verse_num:03d}"
		english_mp3_path = english_directory / f"{basename}.mp3"
		sln_path = sln_directory / f"{basename}e.sln"
		if not english_mp3_path.exists():
			return False
		try:
			(ffmpeg
				.input(str(english_mp3_path))
				.output(str(sln_path), acodec='pcm_s16le', ar='8000', ac=1, f='s16le')
				.overwrite_output()
				.run(capture_stdout=True, capture_stderr=True, quiet=True)
			)
			return True
		except ffmpeg.Error:
			return False"""
	
	"""def cloned_mp3(self, verse):
		basename = f"{verse.chapter.book.number:03d}.{verse.chapter.number:03d}.{verse.number:03d}.mp3"
		return AUDIO_FOLDER / "cloned" / basename
	
	def english_mp3(self, verse):
		basename = f"{verse.chapter.book.number:03d}.{verse.chapter.number:03d}.{verse.number:03d}.mp3"
		return AUDIO_FOLDER / "english" / basename"""



	def export_original_mp3(self, verse):
		if not self.has_original_audio(verse):
			return
		start_time, end_time = self.get_timing(verse)
		basename = f"{verse.chapter.book.number:03d}.{verse.chapter.number:03d}.{verse.number:03d}"
		wav = self.wav(verse.chapter.book.number)
		out = ROOT / "audio" / f"cloned{basename}.mp3"
		(ffmpeg
			.input(str(wav), ss=start_time, to=end_time)
			.output(str(out), format='mp3', audio_bitrate='192k')
			.overwrite_output()
			.run()
		)

	def wav(self, book):
		# the wav of a whole book is a temporary artifact, made from the book's mp3 in SOURCE_AUDIO_FOLDER
		wav = BUILD_FOLDER / "wav" / f"{book:02d}.wav"
		if not wav.exists():
			wav.parent.mkdir(parents=True, exist_ok=True)
			part = wav.with_suffix('.part.wav')
			(ffmpeg
				.input(str(SOURCE_AUDIO_FOLDER / f"{book:02d}.mp3"))
				.output(str(part), acodec='pcm_s16le', ac=1)
				.overwrite_output()
				.run()
			)
			os.replace(part, wav)
		return wav

	def original_mp3(self, verse):
		book, chapter, verse_num = verse.chapter.book.number, verse.chapter.number, verse.number
		return ORIGINAL_AUDIO_FOLDER / f"{book:02d}" / f"{chapter:03d}" / f"{verse_num:03d}.mp3"

	def cloned_mp3(self, verse):
		book, chapter, verse_num = verse.chapter.book.number, verse.chapter.number, verse.number
		return CLONED_AUDIO_FOLDER / f"{book:02d}" / f"{chapter:03d}" / f"{verse_num:03d}.mp3"

	def english_mp3(self, verse):
		book, chapter, verse_num = verse.chapter.book.number, verse.chapter.number, verse.number
		return ENGLISH_AUDIO_FOLDER / f"{book:02d}" / f"{chapter:03d}" / f"{verse_num:03d}.mp3"
