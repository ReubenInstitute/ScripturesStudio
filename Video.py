import os
import ffmpeg
from Overlay import ParashahOverlay, ParashahParagraphSlide, PsalmOverlay, EpisodeOverlay, EpisodeParagraphSlide, PsalmVerseSlide, EpisodeCover
import Media
import Asset
from pathlib import Path

from AudioBible import AudioBible
from Audio import PsalmAudio

ASSETS_FOLDER = Asset.ASSETS_FOLDER
OUTPUT_FOLDER = Asset.OUTPUT_FOLDER
BUILD_FOLDER = Asset.BUILD_FOLDER


class Video(Asset.Asset):
	FADE_DURATION = 0.5
	FPS = 25
	BACKGROUND_OPACITY = 0.7

	def __init__(self, size):
		super().__init__(size)

	def export(self):
		Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
		part = Path(self.filename).with_suffix('.part.mp4')
		video = self.video_stream
		audio = self.audio_stream
#		full_path = os.path.join(OUTPUT_FOLDER, self.filename)
		ffmpeg.output(
			video, 
			audio, 
			str(part), 
			vcodec='libx264', 
			preset='veryfast', 
			crf=23, 
			acodec='aac', 
			audio_bitrate='192k', 
			pix_fmt='yuv420p'
		).run(overwrite_output=True)
		os.replace(part, self.filename)



class EpisodeVideo(Video):
	def __init__(self, episode, size, raw=False):
		super().__init__(size)
		self.episode = episode
		self.raw = raw
		self.audiobible = AudioBible.get_instance()

	@property
	def filename(self):
		suffix = '-raw' if self.raw else ''
		return str(Asset.TORAH_FOLDER / f'torah-{self.episode.parashah.number:02d}.{self.episode.number:02d}{suffix}.mp4')

	def generate_assets(self):
		overlay = EpisodeOverlay(self.episode, size=self.size)
		overlay.export()
		for paragraph in self.episode.paragraphs:
			slide = EpisodeParagraphSlide(self.episode, paragraph.number, size=self.size)
			print (slide)
			slide.export()

	@property
	def audio_stream(self):
		from Audio import EpisodeAudio
		return EpisodeAudio(self.episode).stream

	@property
	def duration(self):
		total = 0.0
		for paragraph in self.episode.paragraphs:
			for verse in paragraph.verses:
				total += self.FADE_DURATION + self.audiobible.cloned_duration(verse) + self.FADE_DURATION
		return total

	def plate(self, name, frames, fade_in=None, fade_out=None):
		image = ffmpeg.input(os.path.join(BUILD_FOLDER, "images", "parashot", name), loop=1, framerate=self.FPS, t=frames / self.FPS)
		image = image.filter('scale', self.width, self.height).filter('format', 'rgba')
		if fade_in:
			image = image.filter('fade', type='in', alpha=fade_in[0], duration=self.FADE_DURATION)
		if fade_out:
			image = image.filter('fade', type='out', alpha=fade_out[0], start_time=frames / self.FPS - self.FADE_DURATION, duration=self.FADE_DURATION)
		return image

	def background(self, start, duration):
		fog_name = "back-720x1280.mp4" if not self.landscape else "back-1280x720.mp4"
		fog_path = os.path.join(ASSETS_FOLDER, fog_name)
		fog_length = float(ffmpeg.probe(fog_path)['format']['duration'])
		background = ffmpeg.input(fog_path, stream_loop=-1, ss=start % fog_length, t=duration)
		background = background.filter('scale', self.width, self.height, force_original_aspect_ratio='increase')
		background = background.filter('crop', w=self.width, h=self.height)
		r, g, b = self.episode.parashah.color
		color_overlay = ffmpeg.input(f'color=c=#{r:02x}{g:02x}{b:02x}:s={self.width}x{self.height}', f='lavfi', t=duration)
		return ffmpeg.filter([background, color_overlay], 'blend', all_mode='overlay', all_opacity=self.BACKGROUND_OPACITY)

	def clip(self, filename, paragraph, verse_index, frames, first, last, first_in_paragraph, last_in_paragraph, start):
		"""One verse as its own small video, so ffmpeg never holds the whole episode in memory."""
		episode = self.episode
		prefix = f"{episode.parashah.number}.{episode.number}.{paragraph.number}"
		background = self.background(start, frames / self.FPS)
		base = self.plate(f"{prefix}.0.png", frames, fade_in=(0,) if first_in_paragraph else None, fade_out=(0,) if last_in_paragraph else None)
		highlight = self.plate(f"{prefix}.{verse_index}.png", frames, fade_in=(1,), fade_out=(1,))
		title = self.plate(f"{episode.parashah.number:02d}_{episode.number:02d}_title.png", frames,
						   fade_in=(0,) if first else None, fade_out=(0,) if last else None)
		video = ffmpeg.overlay(background, ffmpeg.overlay(base, highlight), format='auto', shortest=1)
		video = ffmpeg.overlay(video, title, format='auto', shortest=1)
		ffmpeg.output(video, str(filename), vcodec='libx264', preset='veryfast', crf=23, pix_fmt='yuv420p', r=self.FPS,
					  **{'frames:v': frames}).run(overwrite_output=True)

	def export(self):
		self.generate_assets()
		Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
		folder = Path(BUILD_FOLDER) / "clips" / f"torah-{self.episode.parashah.number:02d}.{self.episode.number:02d}"
		folder.mkdir(parents=True, exist_ok=True)
		verses = self.episode.verses
		units = [(paragraph, verse, i, len(paragraph.verses)) for paragraph in self.episode.paragraphs for i, verse in enumerate(paragraph.verses)]
		clips = []
		elapsed = 0.0
		frames_done = 0
		for n, (paragraph, verse, i, count) in enumerate(units):
			elapsed += self.FADE_DURATION + self.audiobible.cloned_duration(verse) + self.FADE_DURATION
			frames = round(elapsed * self.FPS) - frames_done
			frames_done += frames
			clip = folder / f"{n:03d}.mp4"
			self.clip(clip, paragraph, verses.index(verse) + 1, frames, n == 0, n == len(units) - 1, i == 0, i == count - 1, (frames_done - frames) / self.FPS)
			clips.append(clip)
		list_file = folder / "clips.txt"
		list_file.write_text(''.join(f"file '{clip.resolve()}'\n" for clip in clips))
		video = ffmpeg.input(str(list_file), f='concat', safe=0)
		part = Path(self.filename).with_suffix('.part.mp4')
		ffmpeg.output(video.video, self.audio_stream, str(part), vcodec='copy', acodec='aac', audio_bitrate='192k').run(overwrite_output=True)
		os.replace(part, self.filename)







class PsalmVideo(Video):
	def __init__(self, psalm, size, music=False, graphics=False):
		super().__init__(size)
		self.psalm = psalm
		self.music = music
		self.graphics = graphics
		self.audiobible = AudioBible.get_instance()


	@property
	def basename(self):
		return f'psalm{self.psalm.number:03d}'

	@property
	def filename(self):
		if self.graphics:
			folder = Asset.CINEMATIC_VIDEO_FOLDER
			folder = folder / Asset.HORIZONTAL_SUBFOLDER if self.landscape else folder
		elif self.music:
			folder = Asset.SCORE_VIDEO_FOLDER
			folder = folder / Asset.HORIZONTAL_SUBFOLDER if self.landscape else folder
		else:
			folder = Asset.LIBRARY_VIDEO_FOLDER
		return str(folder / f'{self.basename}.mp4')

	def generate_assets(self):
		overlay = PsalmOverlay(self.psalm, size=self.size)
		overlay.export()
		for paragraph in self.psalm.paragraphs:
			for verse in paragraph.verses:
				slide = PsalmVerseSlide(self.psalm, paragraph.number, verse.number, size=self.size)
				slide.export()

	@property
	def duration(self):
		psalm_audio = PsalmAudio(self.psalm)
		return psalm_audio.duration

	@property
	def background(self):
		duration = self.duration
		if not self.graphics:
			fog_name = "back-720x1280.mp4" if not self.landscape else "back-1280x720.mp4"
			background = ffmpeg.input(os.path.join(ASSETS_FOLDER, fog_name), stream_loop=-1, t=duration)
			background = background.filter('scale', self.width, self.height, force_original_aspect_ratio='increase')
			background = background.filter('crop', w=self.width, h=self.height)
			color_hex = f"#{self.psalm.color[0]:02x}{self.psalm.color[1]:02x}{self.psalm.color[2]:02x}"
			color_overlay = ffmpeg.input(f'color=c={color_hex}:s={self.width}x{self.height}', f='lavfi', t=duration)
			background = ffmpeg.filter([background, color_overlay], 'blend', all_mode='overlay', all_opacity=self.BACKGROUND_OPACITY)
		else:
			custom_bg = os.path.join(ASSETS_FOLDER, f'{self.psalm.number:03d}.mp4')
			if os.path.exists(custom_bg):
				background = ffmpeg.input(custom_bg, stream_loop=-1, t=duration)
				background = background.filter('scale', self.width, self.height, force_original_aspect_ratio='increase')
				background = background.filter('crop', w=self.width, h=self.height)
			else:
				background = ffmpeg.input(f'color=c=black:s={self.width}x{self.height}', f='lavfi', t=duration)
		return background

	@property
	def overlay(self):
		duration = self.duration
		title_image_path = os.path.join(BUILD_FOLDER, "images", "psalms", f"{self.psalm.number:03d}_title.png")
		overlay = ffmpeg.input(title_image_path, loop=1, t=duration)
		overlay = overlay.filter('scale', self.width, self.height)
		overlay = overlay.filter('format', 'rgba')
		overlay = overlay.filter('fade', type='in', start_time=0, duration=self.FADE_DURATION)
		overlay = overlay.filter('fade', type='out', start_time=duration - self.FADE_DURATION, duration=self.FADE_DURATION)
		return overlay

	@property
	def video_stream(self):
		audiobible = self.audiobible
		duration = self.duration

		title_dur = audiobible.title_duration(f'psalm{self.psalm.number:03d}.mp3')
		title_total_duration = self.FADE_DURATION + title_dur + self.FADE_DURATION
		title_video = ffmpeg.input(f'nullsrc=s={self.width}x{self.height}:d={title_total_duration}', f='lavfi')
		title_video = title_video.filter('format', 'rgba')
		title_video = title_video.filter('geq', r='0', g='0', b='0', a='0')


		verse_videos = []
		for paragraph in self.psalm.paragraphs:
			for verse in paragraph.verses:
				if not audiobible.has_cloned_audio(verse):
					continue
				audio_duration = audiobible.cloned_duration(verse)
				if audio_duration == 0.0:
					continue
				if audio_duration < self.FADE_DURATION * 2:
					audio_duration = self.FADE_DURATION * 2
				segment_duration = self.FADE_DURATION + audio_duration + self.FADE_DURATION
				prefix = os.path.join(BUILD_FOLDER, "images", "psalms",
									  f"{self.psalm.number}.{paragraph.number}.{verse.number}")
				# white until a word is spoken, yellow while it is; the timings count from the start of the audio
				shown = []
				now = 0.0
				for number, (start, end) in sorted(audiobible.word_timings(verse).items()):
					start += self.FADE_DURATION
					end += self.FADE_DURATION
					shown += [(f"{prefix}.png", start - now), (f"{prefix}.w{number}.png", end - start)]
					now = end
				shown.append((f"{prefix}.png", segment_duration - now))
				list_path = f"{prefix}.txt"
				with open(list_path, 'w') as f:
					for path, seconds in shown:
						f.write(f"file '{os.path.abspath(path)}'\nduration {seconds:.3f}\n")
					f.write(f"file '{os.path.abspath(shown[-1][0])}'\n")
				verse_video = ffmpeg.input(list_path, f='concat', safe=0).filter('fps', fps=25)
				verse_video = verse_video.filter('scale', self.width, self.height)
				verse_video = verse_video.filter('format', 'rgba')
				verse_video = verse_video.filter('fade', type='in', alpha=1, duration=self.FADE_DURATION)
				verse_video = verse_video.filter('fade', type='out', alpha=1,
												 start_time=segment_duration - self.FADE_DURATION,
												 duration=self.FADE_DURATION)
				verse_videos.append(verse_video)

		all_videos = [title_video] + verse_videos
		if not all_videos:
			video_concat = ffmpeg.input('anullsrc', f='lavfi', t=duration).video.filter('format', 'rgba').filter('geq', r='0', g='0', b='0', a='0')
		else:
			video_concat = ffmpeg.concat(*all_videos, v=1, a=0).node[0]

		video = self.background
		video = ffmpeg.overlay(video, video_concat, format='auto', shortest=1)
		video = ffmpeg.overlay(video, self.overlay, format='auto', shortest=1)
		return video

	@property
	def audio_stream(self):
		from Audio import PsalmAudio
		psalm_audio = PsalmAudio(self.psalm, music=self.music)
#		if psalm_audio.music:
#			return psalm_audio.enhanced_stream
#		else:
		return psalm_audio.stream

	def export(self):
		self.generate_assets()
		super().export()
















































class ParashahVideo(Video):
	def __init__(self, parashah, size):
		super().__init__(size)
		self.parashah = parashah
		self.audiobible = AudioBible.get_instance()

	@property
	def filename(self):
		return str(Asset.TORAH_FOLDER / f'torah-{self.parashah.number:02d}.mp4')

	def generate_assets(self):
		ParashahOverlay(self.parashah, size=self.size).export()
		for number in range(1, len(self.parashah.paragraphs) + 1):
			ParashahParagraphSlide(self.parashah, number, size=self.size).export()

	@property
	def audio_stream(self):
		from Audio import ParashahAudio
		return ParashahAudio(self.parashah).stream

	def plate(self, name, frames, fade_in=None, fade_out=None):
		image = ffmpeg.input(os.path.join(BUILD_FOLDER, "images", "parashot", name), loop=1, framerate=self.FPS, t=frames / self.FPS)
		image = image.filter('scale', self.width, self.height).filter('format', 'rgba')
		if fade_in:
			image = image.filter('fade', type='in', alpha=fade_in[0], duration=self.FADE_DURATION)
		if fade_out:
			image = image.filter('fade', type='out', alpha=fade_out[0], start_time=frames / self.FPS - self.FADE_DURATION, duration=self.FADE_DURATION)
		return image

	def background(self, start, duration):
		fog_name = "back-720x1280.mp4" if not self.landscape else "back-1280x720.mp4"
		fog_path = os.path.join(ASSETS_FOLDER, fog_name)
		fog_length = float(ffmpeg.probe(fog_path)['format']['duration'])
		background = ffmpeg.input(fog_path, stream_loop=-1, ss=start % fog_length, t=duration)
		background = background.filter('scale', self.width, self.height, force_original_aspect_ratio='increase')
		background = background.filter('crop', w=self.width, h=self.height)
		r, g, b = self.parashah.color
		color_overlay = ffmpeg.input(f'color=c=#{r:02x}{g:02x}{b:02x}:s={self.width}x{self.height}', f='lavfi', t=duration)
		return ffmpeg.filter([background, color_overlay], 'blend', all_mode='overlay', all_opacity=self.BACKGROUND_OPACITY)

	def clip(self, filename, paragraph, verse_index, frames, first, last, first_in_paragraph, last_in_paragraph, start):
		"""One verse as its own small video, so ffmpeg never holds the whole parashah in memory."""
		prefix = f"{self.parashah.number}.{paragraph}"
		background = self.background(start, frames / self.FPS)
		base = self.plate(f"{prefix}.0.png", frames, fade_in=(0,) if first_in_paragraph else None, fade_out=(0,) if last_in_paragraph else None)
		highlight = self.plate(f"{prefix}.{verse_index}.png", frames, fade_in=(1,), fade_out=(1,))
		title = self.plate(f"{self.parashah.number:02d}_parashah_title.png", frames,
						   fade_in=(0,) if first else None, fade_out=(0,) if last else None)
		video = ffmpeg.overlay(background, ffmpeg.overlay(base, highlight), format='auto', shortest=1)
		video = ffmpeg.overlay(video, title, format='auto', shortest=1)
		ffmpeg.output(video, str(filename), vcodec='libx264', preset='veryfast', crf=23, pix_fmt='yuv420p', r=self.FPS,
					  **{'frames:v': frames}).run(overwrite_output=True)

	def export(self):
		self.generate_assets()
		Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
		folder = Path(BUILD_FOLDER) / "clips" / f"torah-{self.parashah.number:02d}"
		folder.mkdir(parents=True, exist_ok=True)
		verses = self.parashah.verses
		units = [(number, verse, i, len(paragraph.verses))
				 for number, paragraph in enumerate(self.parashah.paragraphs, 1)
				 for i, verse in enumerate(paragraph.verses)]
		clips = []
		elapsed = 0.0
		frames_done = 0
		for n, (number, verse, i, count) in enumerate(units):
			elapsed += self.FADE_DURATION + self.audiobible.cloned_duration(verse) + self.FADE_DURATION
			frames = round(elapsed * self.FPS) - frames_done
			frames_done += frames
			clip = folder / f"{n:03d}.mp4"
			self.clip(clip, number, verses.index(verse) + 1, frames, n == 0, n == len(units) - 1, i == 0, i == count - 1, (frames_done - frames) / self.FPS)
			clips.append(clip)
		list_file = folder / "clips.txt"
		list_file.write_text(''.join(f"file '{clip.resolve()}'\n" for clip in clips))
		video = ffmpeg.input(str(list_file), f='concat', safe=0)
		part = Path(self.filename).with_suffix('.part.mp4')
		ffmpeg.output(video.video, self.audio_stream, str(part), vcodec='copy', acodec='aac', audio_bitrate='192k').run(overwrite_output=True)
		os.replace(part, self.filename)
