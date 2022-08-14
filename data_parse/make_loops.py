'''
make_loops.py

Implementation of the loop extraction algorithm

Sara Adkins 2022
'''

import guitarpro
import dadagp as dada
import numpy as np

def convert_from_dadagp(tokens):
    song = dada.tokens2guitarpro(tokens, verbose=False)
    song.artist = tokens[0]
    song.album = 'Generated by DadaGP'
    song.title = "untitled"
    return song

#for comparing equality of notes
class MelodyNote:
    def __init__(self, duration, start, bar_start, note_list):
        self.duration = duration.value
        self.is_dotted = duration.isDotted
        self.tick_duration = 3840.0 / self.duration #3840 ticks in whole note
        if self.is_dotted:
            self.tick_duration = self.tick_duration * 1.5
        
        self.start_time = start 
        self.on_bar = False
        if self.start_time == bar_start:
            self.on_bar = True

        self.notes = set(["0:0"])
        self.note_types = set([guitarpro.NoteType.rest])
        if len(note_list) > 0: #not a rest
            self.notes = set([f"{n.string}:{n.value}" for n in note_list])
            self.note_types = set([n.type for n in note_list])

    def __str__(self):
        return f"{self.duration} {self.is_dotted} {self.notes} {self.note_types} at {self.start_time}"
    
    def __eq__(self, other):
        if self.duration != other.duration:
            return False
        if self.is_dotted != other.is_dotted:
            return False
        
        if len(self.notes) != len(other.notes):
            return False
        for m in self.notes:
            if m not in other.notes:
                return False
        
        return True
    
def is_empty_pattern(p):
    for melody in p:
        if melody.note_types !=set([guitarpro.NoteType.rest]):
            return False
    return True

def compare_patterns(p1, p2): #new pattern, existing pattern
    if len(p1) < len(p2):
        for i in range(len(p1)):
            if p1[i] != p2[i]:
                return 0 #not a substring, theres a mismatch
            return 1 #is a substring
    else:
        for i in range(len(p2)):
            if p1[i] != p2[i]:
                return 0 #not a substring, theres a mismatch
            return 2 #existing pattern is substring of the new one, replace it

def test_loop_exists(pattern_list, pattern):
    for i, pat in enumerate(pattern_list):
        result = compare_patterns(pattern, pat)
        if result == 1:
            return -1 #ignore this pattern since its a substring
        if result == 2:
            return i #replace existing pattern with this new longer one
    return None #we're just appending the new pattern

# Convert a GuitarPro song to a list of MelodyNotes to make comparisons quicker
def create_track_list(song):
    melody_track_lists = []
    time_signatures = {}
    for i, track in enumerate(song.tracks):
        melody_list = []
        for measure in track.measures:
            for beat in measure.voices[0].beats:
                note = MelodyNote(beat.duration, beat.start - 960, measure.start - 960, beat.notes) #compensate for GP 960 tick offset
                melody_list.append(note)
            if i == 0:
                signature = (measure.timeSignature.numerator, measure.timeSignature.denominator.value)
                if signature in time_signatures.keys():
                    time_signatures[signature] += 1
                else:
                    time_signatures[signature] = 1
        melody_track_lists.append(melody_list)
        
    return melody_track_lists, time_signatures

# Figure out the dominant key signature in the song
def get_dom_beats_per_bar(time_signatures):
    max_repeats = 0
    dom_sig = None
    for k,v in time_signatures.items():
        if v > max_repeats:
            max_repeats = v
            dom_sig = k
    
    num, dem = dom_sig
    ratio = 4.0 / dem
    return num * ratio

# Implementation of Correlative Matrix approach presented in:
# Jia Lien Hsu, Chih Chin Liu, and Arbee L.P. Chen. Discovering
# nontrivial repeating patterns in music data. IEEE Transactions on
# Multimedia, 3:311–325, 9 2001.
def calc_correlation(track_list, instrument):
    melody_seq = track_list[instrument]
    corr_size = len(melody_seq)
    corr_mat = np.zeros((corr_size, corr_size), dtype='int32')
    corr_dur = np.zeros((corr_size, corr_size), dtype='float')

    for j in range(1, corr_size):
        if melody_seq[0] == melody_seq[j]:
            corr_mat[0,j] = 1
            corr_dur[0,j] = melody_seq[j].tick_duration
        else:
            corr_mat[0,j] = 0
            corr_dur[0,j] = 0
    for i in range(1, corr_size-1):
        for j in range(i+1, corr_size):
            if melody_seq[i] == melody_seq[j]:
                corr_mat[i,j] = corr_mat[i-1, j-1] + 1
                corr_dur[i, j] = corr_dur[i-1, j-1] + melody_seq[j].tick_duration
            else:
                corr_mat[i,j] = 0
                corr_dur[i,j] = 0
    
    return corr_mat, corr_dur, melody_seq

# filter based on defined parameters and remove duplicates
def get_valid_loops(melody_seq, corr_mat, corr_dur, min_len=4, min_beats=16.0, max_beats=32.0, min_rep_beats=4.0):
    x_num_elem, y_num_elem = np.where(corr_mat == min_len)

    valid_indices = []
    for i,x in enumerate(x_num_elem):
        y = y_num_elem[i]
        start_x = x - corr_mat[x,y] + 1
        start_y = y - corr_mat[x,y] + 1
        
        loop_start_time = melody_seq[start_x].start_time
        loop_end_time = melody_seq[start_y].start_time
        loop_beats = (loop_end_time - loop_start_time) / 960.0
        if loop_beats <= max_beats and loop_beats >= min_beats:
            valid_indices.append((x_num_elem[i], y_num_elem[i]))
    
    loops = []
    loop_bp = []
    corr_size = corr_mat.shape[0]
    for start_x,start_y in valid_indices:
        x = start_x
        y = start_y
        while x+1 < corr_size and y+1 < corr_size and corr_mat[x+1,y+1] > corr_mat[x,y]:
            x = x + 1
            y = y + 1
        beginning = x - corr_mat[x,y] + 1
        duration = corr_dur[x,y] / 960.0
        end = y - corr_mat[x,y] + 1
        
        if duration >= min_rep_beats and melody_seq[beginning].on_bar and not is_empty_pattern(melody_seq[beginning:end]):
            loop = melody_seq[beginning:end]
            exist_result = test_loop_exists(loops, loop)
            if exist_result == None:
                loops.append(loop)
                loop_bp.append((melody_seq[beginning].start_time, melody_seq[end].start_time))
            elif exist_result > 0: #index to replace
                loops[exist_result] = loop
                loop_bp[exist_result] = (melody_seq[beginning].start_time, melody_seq[end].start_time)
    
    return loops, loop_bp

# filter out loops below a specified density
def filter_loops_density(token_list, loop_bp, density=3):
    if len(loop_bp) == 0:
        return []
    
    final_endpoints = []
    for pts in loop_bp:
        num_meas = 0
        timestamp = 0
        num_notes = {}
        for i in range(len(token_list)):
            t = token_list[i]
            if "note" in t:
                instrument = t.split(":")[0]
                if instrument not in num_notes:
                    num_notes[instrument] = 1
                else:
                    num_notes[instrument] += 1
            if timestamp >= pts[0] and timestamp < pts[1]:
                if t == "new_measure":
                    num_meas += 1
            if "wait:" in t:
                timestamp += int(t[5:])
            if timestamp >= pts[1]:
                break

        total_notes = 0
        for inst in num_notes.keys():
            total_notes += num_notes[inst]
        curr_density = total_notes * 1.0 / len(num_notes)

        if curr_density >= density * num_meas:
            final_endpoints.append(pts)

    return final_endpoints

#combine all loops into a single DadaGP file, each loop surrounded by repeat tokens
def unify_loops(token_list, loop_bp,density=3):
    if len(loop_bp) == 0:
        return token_list[0:4]

    final_list = token_list[0:4] #header tokens
    for pts in loop_bp:
        #print(pts)
        num_meas = 0
        timestamp = 0
        num_notes = {}
        for i in range(len(token_list)):
            t = token_list[i]
            if "note" in t:
                instrument = t.split(":")[0]
                if instrument not in num_notes:
                    num_notes[instrument] = 1
                else:
                    num_notes[instrument] += 1
            if timestamp >= pts[0] and timestamp < pts[1]:
                if t == "new_measure":
                    num_meas += 1
            if timestamp >= pts[1]:
                break

        total_notes = 0
        for inst in num_notes.keys():
            total_notes += num_notes[inst]
        curr_density = total_notes * 1.0 / len(num_notes)

        if curr_density < density * num_meas:
            continue

        timestamp = 0
        measure_idx = 0
        for i in range(4, len(token_list)):
            t = token_list[i]
            if timestamp >= pts[0] and timestamp < pts[1] and "repeat" not in t:
                final_list.append(t)
                if t == "new_measure":
                    if measure_idx == 0:
                        final_list.append("measure:repeat_open")
                    if measure_idx == num_meas - 1:
                        final_list.append("measure:repeat_close:1")
                    measure_idx += 1
            if "wait:" in t:
                timestamp += int(t[5:])
            if timestamp >= pts[1]:
                break

    final_list.append("measure:repeat_close:1")
    return final_list

# create a new Guitar Pro song with the specified endpoints
def convert_gp_loops(song, endpoints):
    used_tracks = []
    start = endpoints[0]
    end = endpoints[1]
    for inst in range(len(song.tracks)):
        measures = []
        non_rests = 0
        for measure in song.tracks[inst].measures:
            measure.header.isRepeatOpen = False
            measure.header.repeatAlternative = 0
            measure.header.repeatClose = -1
            
            if measure.start >= start and measure.start < end:
                measures.append(measure)
                for beat in measure.voices[0].beats:
                    for note in beat.notes:
                        if note.type != guitarpro.NoteType.rest:
                            non_rests = non_rests + 1
            else:
                valid_beats = []
                for beat in measure.voices[0].beats:
                    if beat.start >= start and beat.start < end:
                        valid_beats.append(beat)
                        for note in beat.notes:
                            if note.type != guitarpro.NoteType.rest:
                                non_rests = non_rests + 1
                if len(valid_beats) > 0:
                    measure.voices[0].beats = valid_beats
                    measures.append(measure)

        if len(measures) > 0 and non_rests > 0:
            song.tracks[inst].measures = measures
            used_tracks.append(song.tracks[inst])
        if inst == 0 and non_rests == 0: #if the loop is just rests, ignore it
            return None
        
    song.tracks = []
    if len(used_tracks) == 0:
        return None
    for track in used_tracks:
        track.measures[0].header.isRepeatOpen = True
        track.measures[len(track.measures) - 1].header.repeatClose = 1
        song.tracks.append(track)
    return song

# extracted only the hard-coded repeats from a DadaGP token list
# includes filtering by loop length and density
def get_repeats(list_words,min_meas=4,max_meas=16,density=8):
    num_words = len(list_words)
    endpoint_dict = {}
    length_dict = {}
    open_reps = []
    curr_length = 0
    curr_notes = {}
    for i in range(num_words-2):
        t = list_words[i]
        if "note" in t:
            instrument = t.split(":")[0]
            if instrument not in curr_notes:
                curr_notes[instrument] = 1
            else:
                curr_notes[instrument] += 1
        if t == "new_measure":
            curr_length += 1
            if list_words[i+1] == "measure:repeat_open":
                curr_length = 1
                curr_notes = {}
                open_reps.append(i)
                endpoint_dict[i] = -1
            if "measure:repeat_close" in list_words[i+1] or "measure:repeat_close" in list_words[i+2]:
                total_notes = 0
                for inst in curr_notes.keys():
                    total_notes += curr_notes[inst]
                if len(curr_notes) == 0:
                    curr_density = 0.0
                else:
                    curr_density = total_notes * 1.0 / len(curr_notes)
                if len(open_reps) > 0:
                    idx = open_reps.pop(len(open_reps) - 1)
                    endpoint_dict[idx] = i
                    length_dict[idx] = (curr_length, curr_density)
                elif len(endpoint_dict) == 0:
                    endpoint_dict[0] = i
                    length_dict[0] = (curr_length, curr_density)

    final_list = []
    if len(endpoint_dict) > 0:
        final_list = [] #list_words[0:4]
        for start in endpoint_dict.keys():
            end = endpoint_dict[start]
            if end <= 0:
                continue
            length_meas = length_dict[start][0]
            length_notes = length_dict[start][1]
            if length_meas < min_meas or length_meas > max_meas or length_notes < density * length_meas:
                continue

            end += 1
            while(end < num_words and end >= 0):
                if list_words[end] == "new_measure":
                    break
                end += 1
            if end > start:
                final_list += list_words[start:end]
    
    return final_list

# calculate the number of hard repeats in a song without saving the loops themselves
def get_num_repeats(list_words,min_meas=4,max_meas=16,density=8):
    num_words = len(list_words)
    endpoint_dict = {}
    length_dict = {}
    open_reps = []
    curr_length = 0
    curr_notes = {}
    for i in range(num_words-2):
        t = list_words[i]
        if "note" in t:
            instrument = t.split(":")[0]
            if instrument not in curr_notes:
                curr_notes[instrument] = 1
            else:
                curr_notes[instrument] += 1
        if t == "new_measure":
            curr_length += 1
            if list_words[i+1] == "measure:repeat_open":
                curr_length = 1
                curr_notes = {}
                open_reps.append(i)
                endpoint_dict[i] = -1
            if "measure:repeat_close" in list_words[i+1] or "measure:repeat_close" in list_words[i+2]:
                total_notes = 0
                for inst in curr_notes.keys():
                    total_notes += curr_notes[inst]
                if len(curr_notes) == 0:
                    curr_density = 0.0
                else:
                    curr_density = total_notes * 1.0 / len(curr_notes)
                if len(open_reps) > 0:
                    idx = open_reps.pop(len(open_reps) - 1)
                    endpoint_dict[idx] = i
                    length_dict[idx] = (curr_length, curr_density)
                elif len(endpoint_dict) == 0:
                    endpoint_dict[0] = i
                    length_dict[0] = (curr_length, curr_density)

    num_repeats = 0
    for start in endpoint_dict.keys():
        end = endpoint_dict[start]
        if end <= 0:
            continue
        length_meas = length_dict[start][0]
        length_notes = length_dict[start][1]
        if length_meas < min_meas or length_meas > max_meas or length_notes < density * length_meas:
            continue

        num_repeats += 1
    
    return num_repeats
