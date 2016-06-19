from collections import Counter
from itertools import product
import musicbrainzngs
import os
import re
import subprocess
import argparse
import pickle

discoveries_file = os.path.expanduser(r'~\AppData\Local\MusicSorter\discoveries.p')
ignore_list = ['wwwdownvidscom', 'wwwdownvidsnet', 'mp3', 'lyrics', 'with', 'hq', 'hd', 'studio', 'version', 'by', 'official', 'music', 'video', 'album', 'and', 'audio', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

def get_release_list(artist_str):
    """ Gets a release list from musicbrains API. """
    username = 'Username'
    password = 'Password'
    
    musicbrainzngs.set_useragent(username, password)
    artist_list = musicbrainzngs.search_artists(artist=artist_str)['artist-list']
    artist = sorted(artist_list, reverse=True, key=lambda artist:int(artist['ext:score']))[0]
    artist_id = artist['id']

    limit = 100
    offset = 0
    release_list = []
    release_count = 1

    while offset < release_count:
        print 'Requesting tracks {0} - {1}'.format(str(offset), str(offset+limit))
        result = musicbrainzngs.browse_releases(artist=artist_id, release_status=['official'], release_type=['album'], includes=['recordings'], limit=limit, offset=offset)
        release_count = result['release-count']
        release_list += result['release-list']
        offset += limit
    
    return release_list

def get_discovery(artist_str):
    """
    Returns a set of all release album songs by the artist. The result is the format {(album, title, track number, track length), ... }
    """
    try:
        discoveries = pickle.load(open(discoveries_file, 'rb'))
    except IOError:
        discoveries = {}
    try:
        return discoveries[artist_str]
    except KeyError:
        release_list = get_release_list(artist_str)
        albums = {}
        for album in release_list:
            album_title = album['title']
            for medium in album['medium-list']:
                for track in medium['track-list']:
                    track_number = track['number']
                    if not track_number.isdigit():
                        continue
                    recording = track['recording']
                    try:
                        track_length = recording['length']
                    except KeyError:
                        track_length = None
                    track_title  = track['recording']['title']
                    try:
                        albums[album_title][track_title] += [(track_number, track_length)]
                    except KeyError:
                        try:
                            albums[album_title][track_title]  = [(track_number, track_length)]
                        except KeyError:
                            albums[album_title] = {track_title: [(track_number, track_length)]}
        
        discovery = set()
        for album_title, album in albums.iteritems():
            for track_title, track in album.iteritems():
                track = [x for x in track if x[0].isdigit()] or track
                number, length = Counter(track).most_common(1)[0][0]
                album_title = u'{0}'.format(album_title)
                track_title = u'{0}'.format(track_title)
                number      = u'{0}'.format(number)
                length      = u'{0}'.format(length)
                discovery.add((album_title, track_title, number, length))
        
        discoveries[artist_str] = discovery
        directory = os.path.dirname(discoveries_file)
        if not os.path.exists(directory):
            os.makedirs(directory)
        pickle.dump(discoveries, open(discoveries_file, "wb"))
        return discovery

def to_lower_alphanumeric(s):
    """ Converts a string to a lower case alphanumeric only string. """
    s = s.encode('ascii','ignore')
    s = filter(str.isalnum, s)
    return s.lower()

def remove_substrs(s, remove_list):
    """ Removes all matching sub-strings in the remove list. """
    for r in remove_list:
        s = s.replace(r, '')
    return s

def filename_matches_track(filename, track_str, *info):
    """ Returns True if the filename is similar to the track_str. """
    def simplify(s):
        s = to_lower_alphanumeric(s)
        s = remove_substrs(s, ignore_list)
        return s
    filename = simplify(filename)
    track_str = simplify(track_str)
    info = [simplify(x) for x in info]
    p1 = '('+'|'.join(info)+')*'
    regex = '^' + p1 + track_str + p1 + '$'
    if re.match(regex, filename):
        return True
    return False

def tag_and_rename_file(filename, artist_str, album_str, track_str, track_number):
    """ New filename format is "01 - track_str.mp3" (assuming track_number is 1 and filename is an mp3). """
    track_str = track_str.encode('ascii', 'ignore')
    new_filename = '{0:0=2d} - {1}.mp3'.format(int(track_number), track_str)
    new_filename = remove_substrs(new_filename,  [r'\\', r'/', r':', r'*', r'?', r'"', r',<', r'>', r'|'])
    i = 0
    suffix = ''
    while True:
        if new_filename == filename:
            break
        if not os.path.exists(new_filename):
            print 'Moving {0} to {1}'.format(filename, new_filename)
            os.rename(filename, new_filename)
            break
        i += 1
        suffix = ' ({0})'.format(str(i))
        new_filename = (suffix+'.').join(filename.rsplit('.', -1))
    print 'Tagging "{0}"'.format(new_filename, artist_str, album_str, track_str, track_number)
    p = subprocess.call(['id3', '-a', artist_str, '-l', album_str, '-t', track_str, '-n', track_number, new_filename])

def tag_and_rename_matching_files(artist_str, album_str, files):
    discovery = get_discovery(artist_str)
    if not discovery:
        print 'No match found for artist "{0}"'.format(artist_str)
        return
    tracks = {x[1]: (x[2], x[3]) for x in discovery if to_lower_alphanumeric(x[0]) == to_lower_alphanumeric(album_str)}
    if not tracks:
        print 'No match found for album "{0}". Available albums:'.format(album_str)
        for album in {x[0] for x in discovery}:
            print '{0}'.format(album.encode('ascii','ignore'))
        return
    
    unmatched_files = []
    for filename in files:
        matches = []
        for track_str in tracks:
            if filename_matches_track(filename, track_str, artist_str, album_str):
                matches.append(track_str)
        if len({to_lower_alphanumeric(x) for x in matches}) == 1:
            track_str = matches[0]
            track_number = tracks[track_str][0]
            tag_and_rename_file(filename, artist_str, album_str, track_str, track_number)
        else:
            unmatched_files.append(filename)
    if unmatched_files:
        print 'No match found for file some files. Available tracks:'
        tracks = sorted(tracks.items(), key=lambda x: x[1][0].isdigit() and int(x[1][0]))
        for track_str, (number, _) in tracks:
            print '{0:>2}: {1}'.format(number, track_str.encode('ascii','ignore'))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Organize album folder.')
    parser.add_argument('artist', help='The name of the artist/band')
    parser.add_argument('album', help='The name of the album')
    args = parser.parse_args()
    tag_and_rename_matching_files(args.artist, args.album, os.listdir('.'))


    
