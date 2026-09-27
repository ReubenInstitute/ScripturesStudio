#!/usr/bin/env python3
from flask import Flask, send_file, request, Response, render_template, redirect, url_for, abort
import ffmpeg
from Bible import Bible
import Hebrew
from Video import PsalmVideo, EpisodeVideo, ParashahVideo
import Media
import re
import io
import os
import csv
from pathlib import Path
from Asset import STATIC_FOLDER, TEMPLATES_FOLDER
from Overlay import PsalmCover, ParashahCover, PsalmVerseSlide, PsalmVersePreview, ParashahVersePreview
from Audio import PsalmAudio, ParashahAudio
from Psalms import Psalms
from Parashot import Parashot
from AudioBible import AudioBible

app = Flask(__name__, template_folder=str(TEMPLATES_FOLDER))
bible = Bible()
bible.psalms = Psalms(bible)
bible.parashot = Parashot(bible)

@app.context_processor
def template_globals():
	return dict(len=len)

def format_duration(seconds):
	if seconds <= 0:
		return ""
	h = int(seconds // 3600)
	m = int((seconds % 3600) // 60)
	s = int(seconds % 60)
	if h:
		return f"{h}:{m:02d}:{s:02d}"
	return f"{m}:{s:02d}"

def audio_totals(verses, audio):
	total_original = 0.0
	total_cloned = 0.0
	for verse in verses:
		if audio.has_original_audio(verse):
			start, end = audio.get_timing(verse)
			total_original += (end - start)
		if audio.has_cloned_audio(verse):
			total_cloned += audio.cloned_duration(verse)
	return total_original, total_cloned

@app.route('/')
def index():
	audio = AudioBible.get_instance()

	book_ranges = [
		(1, 41, "Book 1"),
		(42, 72, "Book 2"),
		(73, 89, "Book 3"),
		(90, 106, "Book 4"),
		(107, 150, "Book 5")
	]

	books_data = []
	grand_original = 0.0
	grand_cloned = 0.0
	grand_total_duration = 0.0

	for start, end, name in book_ranges:
		book_psalms = []
		book_original = 0.0
		book_cloned = 0.0
		book_total_duration = 0.0

		for i in range(start, end + 1):
			psalm = bible.psalms[i - 1]
			total_original, total_cloned = audio_totals(psalm.verses, audio)

			book_original += total_original
			book_cloned += total_cloned

			psalm_audio = PsalmAudio(psalm, music=True)
			total_dur = psalm_audio.duration
			book_total_duration += total_dur

			book_psalms.append({
				"psalm": psalm,
				"cloned_duration": format_duration(total_cloned),
				"original_duration": format_duration(total_original),
				"total_duration": format_duration(total_dur),
				"show_color": total_cloned > 0
			})

		grand_original += book_original
		grand_cloned += book_cloned
		grand_total_duration += book_total_duration

		books_data.append({
			"name": name,
			"psalms": book_psalms,
			"cloned_total": format_duration(book_cloned),
			"original_total": format_duration(book_original),
			"duration_total": format_duration(book_total_duration)
		})

	parashot_data = []
	for parashah_obj in bible.parashot:
		total_original, total_cloned = audio_totals(parashah_obj.verses, audio)
		parashot_data.append({
			"parashah": parashah_obj,
			"original_duration": format_duration(total_original),
			"cloned_duration": format_duration(total_cloned),
		})

	return render_template('index.html',
		psalms=bible.psalms,
		books=books_data,
		grand_original_formatted=format_duration(grand_original),
		grand_cloned_formatted=format_duration(grand_cloned),
		grand_total_formatted=format_duration(grand_total_duration),
		parashot=parashot_data
	)

@app.route('/psalms/<int:p>')
def psalm(p):
	psalm = bible.psalms[p-1]
	psalm.load()
	audio = AudioBible.get_instance()

	template = open('descriptions.md', 'r', encoding='utf-8').read()
	templates = {}
	for match in re.finditer(r'##([^\n]+)\n([\s\S]*?)(?=(?:^##|\Z))', template, re.MULTILINE):
		name = match.group(1).strip()
		text = match.group(2).strip()
		templates[name] = text
	descriptions = {}
	for name, template_text in templates.items():
		from jinja2 import Template
		text = Template(template_text).render(psalm=psalm)
		descriptions[name] = text

	return render_template('psalm.html',
		p=p,
		psalm=psalm,
		bible=bible,
		audio=audio,
		descriptions=descriptions
	)

@app.route('/psalms/<int:p>/edit', methods=['GET'])
def psalm_edit(p):
	psalm = bible.psalms[p-1]
	psalm.load()
	return render_template('psalm_edit.html', psalm=psalm, p=p)

@app.route('/psalms/<int:p>/edit', methods=['POST'])
def psalm_save(p):
	psalm = bible.psalms[p-1]
	text = request.form.get('text', '').replace('\r\n', '\n')
	psalm.markdown = text
	psalm.load()
	return redirect(f'/psalms/{p}')

@app.route('/psalms/<int:p>/align')
def psalm_align(p):
	psalm = bible.psalms[p-1]
	psalm.load()
	alignment_path = 'csv/alignment.csv'
	verse_data = []

	align_rows = []
	if os.path.exists(alignment_path):
		with open(alignment_path, 'r', encoding='utf-8') as f:
			reader = csv.DictReader(f)
			for row in reader:
				if int(row['book']) == 27 and int(row['chapter']) == p:
					align_rows.append({
						'verse': int(row['verse']),
						'word': int(row['word']),
						'start': float(row['start']),
						'end': float(row['end'])
					})

	for verse in psalm.verses:
		words = verse.bare_text.split()
		verse_words = []
		for idx, word_text in enumerate(words, start=1):
			match = next((r for r in align_rows if r['verse'] == verse.number and r['word'] == idx), None)
			if match:
				start = match['start']
				end = match['end']
				duration = end - start
				start_str = f"{start:.3f}"
				end_str = f"{end:.3f}"
				duration_str = f"{duration:.3f}"
			else:
				start_str = end_str = duration_str = ''
			verse_words.append({
				'index': idx,
				'text': word_text,
				'start': start_str,
				'end': end_str,
				'duration': duration_str
			})
		verse_data.append({
			'number': verse.number,
			'words': verse_words
		})

	return render_template('psalm-align.html', p=p, psalm=psalm, verse_data=verse_data)

@app.route('/psalms/<int:p>/<int:v>/audio')
def psalm_audio_edit(p, v):
	psalm = bible.psalms[p - 1]
	psalm.load()
	verse = psalm.verses[v - 1]
	audio = AudioBible.get_instance()

	if audio.has_original_audio(verse):
		start, end = audio.get_timing(verse)
	else:
		start, end = 0.0, 0.0

	if not start:
		if v > 1:
			prev_verse = psalm.verses[v - 2]
		else:
			prev_psalm = bible.psalms[p - 2] if p > 1 else None
			prev_verse = prev_psalm.verses[-1] if prev_psalm else None
		if prev_verse:
			s, e = audio.get_timing(prev_verse)
			start = e
			end = start + 15

	frm = max(0, start - 2)
	to = end + 15 if end > 0 else 15

	next_verse = v + 1 if v < len(psalm.verses) else None
	next_chapter = p + 1 if not next_verse and p < 150 else None

	return render_template(
		'psalm_audio_edit.html',
		p=p, v=v, start=start, end=end, frm=frm, to=to,
		psalm=psalm, verse=verse,
		next_verse=next_verse, next_chapter=next_chapter
	)

@app.route('/psalms/save-psalm-audio-timing', methods=['POST'])
def save_psalm_audio_timing():
	book = int(request.form['book'])
	chapter = int(request.form['chapter'])
	verse_num = int(request.form['verse'])
	start = float(request.form['start'])
	end = float(request.form['end'])

	verse = bible.verse(book - 1, chapter, verse_num)
	audio = AudioBible.get_instance()
	audio.set_timing(verse, start, end)

	if 'next' in request.form:
		if 'next_verse' in request.form:
			next_verse = int(request.form['next_verse'])
			return redirect(f'/psalms/{chapter}/{next_verse}/audio')
		elif 'next_chapter' in request.form:
			next_chapter = int(request.form['next_chapter'])
			return redirect(f'/psalms/{next_chapter}/1/audio')
	return redirect(f'/psalms/{chapter}/{verse_num}/audio')

@app.route('/psalms/preview/psalm/<int:p>/cover.png', defaults={'size': Media.SDV})
@app.route('/psalms/preview/psalm/<int:p>/cover/horizontal.png', defaults={'size': Media.SDH})
def preview_psalm_cover(p, size):
	if not 1 <= p <= 150:
		abort(404)
	image = PsalmCover(bible.psalms[p - 1], size).image
	png = io.BytesIO()
	image.save(png, 'PNG')
	return Response(png.getvalue(), mimetype='image/png', headers={'Cache-Control': 'no-store'})

@app.route('/psalms/preview/psalm/<int:p>/<int:paragraph>/<int:verse>.png', defaults={'size': Media.SDV})
@app.route('/psalms/preview/psalm/<int:p>/<int:paragraph>/<int:verse>/horizontal.png', defaults={'size': Media.HDH})
def preview_psalm_verse(p, paragraph, verse, size):
	if not 1 <= p <= 150:
		abort(404)
	psalm = bible.psalms[p - 1]
	if not 1 <= paragraph <= len(psalm.paragraphs) or verse not in [v.number for v in psalm.paragraphs[paragraph - 1].verses]:
		abort(404)
	image = PsalmVersePreview(PsalmVerseSlide(psalm, paragraph, verse, size), size).image
	png = io.BytesIO()
	image.save(png, 'PNG')
	return Response(png.getvalue(), mimetype='image/png', headers={'Cache-Control': 'no-store'})

@app.route('/psalms/export/covers/<int:psalm_number>')
def export_psalm_covers(psalm_number):
	psalm = bible.psalms[psalm_number - 1]
	for size in (Media.SDV, Media.SDH, Media.SD):
		cover = PsalmCover(psalm, size)
		if cover.image is not None:
			cover.export()
	return redirect(f'/psalms/{psalm_number}')

@app.route('/psalms/export/covers')
def export_all_psalm_covers():
	for number in range(1, 151):
		psalm = bible.psalms[number - 1]
		for size in (Media.SDV, Media.SDH, Media.SD):
			cover = PsalmCover(psalm, size)
			if cover.image is not None:
				cover.export()
	return redirect('/')

@app.route('/psalms/export/audio/<int:number>')
def export_psalm_audio(number):
	psalm = bible.psalms[number - 1]
	PsalmAudio(psalm).export()
	return redirect(f'/psalms/{number}')

@app.route('/psalms/export/audio/score/<int:number>')
def export_psalm_score_audio(number):
	psalm = bible.psalms[number - 1]
	PsalmAudio(psalm, music=True).export()
	return redirect(f'/psalms/{number}')

@app.route('/psalms/export/audio')
def export_psalms_audio():
	for i in range(150):
		psalm = bible.psalms[i]
		PsalmAudio(psalm).export()
	return redirect('/')

@app.route('/psalms/export/video/horizontal/<int:p>')
def export_psalm_horizontal_video(p):
	psalm = bible.psalms[p - 1]
	video = PsalmVideo(psalm, size=Media.HDH)
	video.export()
	return redirect(f'/psalms/{p}')

@app.route('/psalms/export/video/score/<int:p>')
def export_psalm_score_video(p):
	psalm = bible.psalms[p - 1]
	video = PsalmVideo(psalm, size=Media.SDV, music=True)
	video.export()
	return redirect(f'/psalms/{p}')

@app.route('/psalms/export/video/score/horizontal/<int:p>')
def export_psalm_score_horizontal_video(p):
	psalm = bible.psalms[p - 1]
	video = PsalmVideo(psalm, size=Media.HDH, music=True)
	video.export()
	return redirect(f'/psalms/{p}')

@app.route('/psalms/export/video/cinematic/<int:p>')
def export_psalm_cinematic_video(p):
	psalm = bible.psalms[p - 1]
	video = PsalmVideo(psalm, size=Media.SDV, music=True, graphics=True)
	video.export()
	return redirect(f'/psalms/{p}')

@app.route('/psalms/clone/<int:p>')
def clone_psalm_voice(p):
	psalm = bible.psalms[p - 1]
	audio = AudioBible.get_instance()
	for verse in psalm.verses:
		if not audio.has_cloned_audio(verse) and audio.has_original_audio(verse):
			audio.clone(verse)  # note: AudioBible now has a clone(verse) method
	return redirect(f'/psalms/{p}')

@app.route('/psalms/align/<int:p>')
def align_psalm(p):
	audio = AudioBible.get_instance()
	psalm = bible.psalms[p - 1]
	for verse in psalm.verses:
		if audio.has_cloned_audio(verse):
			audio.align(verse)
	return redirect(f'/psalms/{p}')

@app.route('/psalms/align/<int:p>/<int:v>')
def align_psalm_verse(p, v):
	audio = AudioBible.get_instance()
	psalm = bible.psalms[p - 1]
	verse = psalm.verses[v - 1]
	if audio.has_cloned_audio(verse):
		audio.align(verse)
	return redirect(f'/psalms/{p}#{v}')

@app.route('/parashot/<int:number>')
def parashah(number):
	parashah = bible.parashot[number-1]
	audio = AudioBible.get_instance()
	episodes_data = []
	for episode_obj in parashah.episodes:
		total_original, total_cloned = audio_totals(episode_obj.verses, audio)
		episodes_data.append({
			"episode": episode_obj,
			"original_duration": format_duration(total_original),
			"cloned_duration": format_duration(total_cloned),
		})
	return render_template('parashah.html', parashah=parashah, episodes=episodes_data)

@app.route('/parashot/<int:number>/edit', methods=['GET'])
def parashah_edit(number):
	parashah = bible.parashot[number-1]
	return render_template('parashah_edit.html', parashah=parashah)

@app.route('/parashot/<int:number>/edit', methods=['POST'])
def parashah_save(number):
	parashah = bible.parashot[number-1]
	text = request.form.get('text').replace('\r\n', '\n')
	text = Hebrew.normalize(text=text)
	parashah.markdown = text
	return redirect(f'/parashot/{parashah.number}')

@app.route('/parashot/<int:number>/<int:episode>')
def episode(number, episode):
	parashah = bible.parashot[number-1]
	episode = parashah.episodes[episode-1]
	audio = AudioBible.get_instance()
	total_original, total_cloned = audio_totals(episode.verses, audio)
	return render_template('episode.html',
		episode=episode,
		audio=audio,
		total_original_mmss=format_duration(total_original),
		total_cloned_mmss=format_duration(total_cloned)
	)

@app.route('/parashot/<int:number>/export-audio')
def export_parashah_audio(number):
	parashah = bible.parashot[number-1]
	ParashahAudio(parashah).export_mp3()
	return redirect(f'/parashot/{number}')

@app.route('/parashot/<int:parashah_num>/<int:episode_num>/<int:v>/audio')
def parashah_verse_audio_edit(parashah_num, episode_num, v):
	parashah = bible.parashot[parashah_num - 1]
	episode = parashah.episodes[episode_num - 1]
	verse = episode.verses[v - 1]
	prev_verse = episode.verses[v - 2] if v > 1 else None
	if not prev_verse:
		if parashah_num > 1:
			prev_parashah = bible.parashot[parashah_num - 2]
			prev_verse = prev_parashah.verses[-1]
	next_verse = episode.verses[v] if v < len(episode.verses) else None
	audio = AudioBible.get_instance()
	start, end = audio.get_timing(verse)
	if not start:
		if prev_verse:
			s, e = audio.get_timing(prev_verse)
			start = e
			end = start + 15
	frm = max(0, start - 2)
	to = end + 15 if end > 0 else 15

	return render_template('parashah_verse_audio_edit.html',
		parashah=parashah, episode=episode, v=v, verse=verse,
		start=start, end=end, frm=frm, to=to, next_verse=next_verse)

@app.route('/parashot/save-parashah-audio-timing', methods=['POST'])
def save_parashah_audio_timing():
	book_num = int(request.form['book'])
	chapter_num = int(request.form['chapter'])
	idx = int(request.form['verse'])
	start = float(request.form['start'])
	end = float(request.form['end'])
	parashah_num = int(request.form['parashah'])
	episode_num = int(request.form['episode'])

	book = bible.books[book_num - 1]
	parashah = bible.parashot[parashah_num - 1]
	episode = parashah.episodes[episode_num - 1]
	verse = episode.verses[idx - 1]
	audio = AudioBible.get_instance()
	audio.set_timing(verse, start, end)

	if 'next' in request.form and 'next_verse' in request.form:
		next_verse = int(request.form['next_verse'])
		return redirect(f'/parashot/{parashah.number}/{episode.number}/{next_verse}/audio')
	return redirect(f'/parashot/{parashah.number}/{episode.number}/{idx - 1}/audio')

@app.route('/parashot/preview/parashah/<int:number>/cover.png')
def preview_parashah_cover(number):
	if not 1 <= number <= 54:
		abort(404)
	png = io.BytesIO()
	ParashahCover(bible.parashot[number-1], Media.SDH).image.save(png, 'PNG')
	return Response(png.getvalue(), mimetype='image/png', headers={'Cache-Control': 'no-store'})

@app.route('/parashot/preview/parashah/<int:number>/<int:paragraph>/<int:verse>.png')
def preview_parashah_verse(number, paragraph, verse):
	if not 1 <= number <= 54:
		abort(404)
	paragraphs = bible.parashot[number-1].paragraphs
	if not 1 <= paragraph <= len(paragraphs):
		abort(404)
	if not 1 <= verse <= len(bible.parashot[number-1].verses):
		abort(404)
	image = ParashahVersePreview(bible.parashot[number-1], paragraph, verse, Media.SDH).image
	png = io.BytesIO()
	image.save(png, 'PNG')
	return Response(png.getvalue(), mimetype='image/png', headers={'Cache-Control': 'no-store'})

@app.route('/parashot/export/covers/<int:number>')
def export_parashah_covers(number):
	ParashahCover(bible.parashot[number-1], Media.SDH).export()
	return redirect(f'/parashot/{number}')

@app.route('/parashot/generate/video/<int:parashah>/full')
def generate_parashah_video(parashah):
	ParashahVideo(bible.parashot[parashah-1], size=Media.SDH).export()
	return redirect(f'/parashot/{parashah}')

@app.route('/parashot/generate/video/<int:parashah>/<int:episode>')
def generate_episode_video(parashah, episode):
	parashah_obj = bible.parashot[parashah-1]
	episode_obj = parashah_obj.episodes[episode-1]
	video = EpisodeVideo(episode_obj, size=Media.SDV)
	video.export()
	return redirect(f'/parashot/{parashah}/{episode}')

@app.route('/parashot/clone/<int:parashah>/<int:episode>')
def clone_episode_voice(parashah, episode):
	parashah_obj = bible.parashot[parashah-1]
	episode_obj = parashah_obj.episodes[episode-1]
	audio = AudioBible.get_instance()
	for verse in episode_obj.verses:
		if not audio.has_cloned_audio(verse) and audio.has_original_audio(verse):
			audio.clone(verse)
	return redirect(f'/parashot/{parashah}/{episode}')

@app.route('/parashot/clone/<int:book>/<int:chapter>/<int:verse>')
def clone_verse(book, chapter, verse):
	verse_obj = bible.verse(book - 1, chapter, verse)
	audio = AudioBible.get_instance()
	if audio.has_original_audio(verse_obj):
		audio.clone(verse_obj)
	return redirect(request.referrer or '/')

@app.route('/parashot/align/<int:book>/<int:chapter>/<int:verse>')
def align_verse(book, chapter, verse):
	audio = AudioBible.get_instance()
	verse_obj = bible.verse(book - 1, chapter, verse)
	if audio.has_cloned_audio(verse_obj):
		audio.align(verse_obj)
	return redirect(request.referrer or '/')

@app.route('/parashot/align/<int:book>/<int:chapter>')
def align_chapter(book, chapter):
	book_obj = bible[book - 1]
	chapter_obj = book_obj[chapter - 1]
	audio = AudioBible.get_instance()
	for verse in chapter_obj.verses:
		if audio.has_cloned_audio(verse):
			audio.align(verse)
	return redirect(request.referrer or '/')

@app.route('/audio-<int:book>-<string:frm>-<string:to>.wav')
def serve_audio_segment(book, frm, to):
	frm = float(frm)
	to = float(to)
	audio_path = AudioBible.get_instance().wav(book)
	process = (
		ffmpeg
		.input(audio_path, ss=frm, to=to)
		.output('pipe:', acodec='pcm_s16le', ar=44100, ac=1, format='wav')
		.run_async(pipe_stdout=True, pipe_stderr=True)
	)
	audio_data, _ = process.communicate()
	return Response(audio_data, mimetype='audio/wav')

@app.route('/hebrew/normalize', methods=['POST'])
def hebrew_normalize():
	text = request.form.get('text', '')
	normalized = Hebrew.normalize(text)
	return Response(normalized, mimetype='text/plain')

@app.route('/hebrew/dagesh_hazzak', methods=['POST'])
def hebrew_dagesh_hazzak():
	text = request.form.get('text', '')
	processed = Hebrew.add_dagesh_hazzak(text)
	return Response(processed, mimetype='text/plain')

@app.route('/<path:filename>')
def serve_file(filename):
	path = STATIC_FOLDER / filename
	if path.exists():
		return send_file(path)
	else:
		abort(404)

if __name__ == '__main__':
	app.run(host='0.0.0.0', debug=True, port=5000)
