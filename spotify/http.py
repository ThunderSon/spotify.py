##
# -*- coding: utf-8 -*-
##
import asyncio
import json
from base64 import b64encode
from urllib.parse import quote

import aiohttp

from .errors import HTTPException, Forbidden, NotFound


class Route:
    BASE = 'https://api.spotify.com/v1'

    def __init__(self, method, path, **kwargs):
        self.path = path
        self.method = method
        self.url = (self.BASE + self.path)

        if kwargs:
            parameters = {key: (quote(v) if isinstance(v, str) else v) for key, v in kwargs.items()}
            self.url = self.url.format(**parameters)


class HTTPClient:
    '''Represents an HTTP client sending HTTP requests to the Spotify API.'''

    RETRY_AMOUNT = 10

    def __init__(self, client_id, client_secret, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self.loop)

        self.client_id = client_id
        self.client_secret = client_secret

        self.bearer_info = None
        self.token = None

    async def get_bearer_info(self):
        '''gets the application bearer token from client_id and client_secret'''
        url = 'https://accounts.spotify.com/api/token'
        if self.client_id is None:
            raise KeyError('HTTPClient has no client id, while performing a non user based request.')

        basic = 'Basic ' + b64encode('{0}:{1}'.format(self.client_id, self.client_secret).encode()).decode()
        headers = {'Authorization': basic}
        payload = {'grant_type': 'client_credentials'}

        async with self._session.post(url, data=payload, headers=headers) as r:
            data = json.loads(await r.text(encoding='utf-8'))

        return data

    async def request(self, route, **kwargs):
        if self.bearer_info is None:
            self.bearer_info = await self.get_bearer_info()
            self.token = self.bearer_info.get('access_token')

        method = route.method
        url = route.url

        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': kwargs.get('content_type', 'application/json')}

        for _ in range(self.RETRY_AMOUNT):
            r = await self._session.request(method, url, headers=headers, **kwargs)
            try:
                status = r.status
                data = json.loads(await r.text(encoding='utf-8'))

                if 300 > status >= 200:
                    return data

                if status == 429:
                    # we're being rate limited.
                    amount = r.headers.get('Retry-After')
                    print('Rate limited:', amount)
                    await asyncio.sleep(int(amount), loop=self.loop)
                    continue

                if status in (502, 503):
                    # unconditional retry
                    continue

                if status == 403:
                    raise Forbidden(r, data)
                elif status == 404:
                    raise NotFound(r, data)
            finally:
                await r.release()

        return HTTPException(r, data)

    async def close(self):
        await self._session.close()

    async def album(self, spotify_id, market='US'):
        route = Route('GET', '/albums/{spotify_id}', spotify_id=spotify_id)
        payload = {}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def album_tracks(self, spotify_id, limit=20, offset=0, market='US'):
        route = Route('GET', '/albums/{spotify_id}/tracks', spotify_id=spotify_id)
        payload = {'limit': limit, 'offset': offset}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def albums(self, spotify_ids, market='US'):
        route = Route('GET', '/albums/')
        payload = {'ids': spotify_ids}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def artist(self, spotify_id):
        route = Route('GET', '/artists/{spotify_id}', spotify_id=spotify_id)
        return await self.request(route)

    async def artist_albums(self, spotify_id, include_groups=None, limit=20, offset=0, market='US'):
        route = Route('GET', '/artists/{spotify_id}/albums', spotify_id=spotify_id)
        payload = {'limit': limit, 'offset': offset}

        if include_groups:
            payload['include_groups'] = include_groups

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def artist_top_tracks(self, spotify_id, country):
        route = Route('GET', '/artists/{spotify_id}/top-tracks', spotify_id=spotify_id)
        payload = {'country': country}
        return await self.request(route, params=payload)

    async def artist_related_artists(self, spotify_id):
        route = Route('GET', '/artists/{spotify_id}/related-artists', spotify_id=spotify_id)
        return await self.request(route)

    async def artists(self, spotify_ids):
        route = Route('GET', '/artists')
        payload = {'ids': spotify_ids}
        return await self.request(route, params=payload)

    async def category(self, category_id, country=None, locale=None):
        route = Route('GET', '/browse/categories/{category_id}', category_id=category_id)
        payload = {}

        if country:
            payload['country'] = country

        if locale:
            payload['locale'] = locale 

        return await self.request(route, params=payload)

    async def category_playlists(self, category_id, limit=20, offset=0, country=None):
        route = Route('GET', '/browse/categories/{category_id}/playlists', category_id=category_id)
        payload = {'limit': limit, 'offset': offset}

        if country:
            payload['country'] = country

        return await self.request(route, params=payload)

    async def categories(self, limit=20, offset=0, country=None, locale=None):
        route = Route('GET', '/browse/categories')
        payload = {'limit': limit, 'offset': offset}

        if country:
            payload['country'] = country

        if locale:
            payload['locale'] = locale

        return await self.request(route, params=payload)

    async def featured_playlists(self, locale=None, country=None, timestamp=None, limit=20, offset=0):
        route = Route('GET', '/browse/featured-playlists')
        payload = {'limit': limit, 'offset': offset}

        if country:
            payload['country'] = country

        if locale:
            payload['locale'] = locale

        if timestamp:
            payload['timestamp'] = timestamp

        return await self.request(route, params=payload)

    async def new_releases(self, *, country=None, limit=20, offset=0):
        route = Route('GET', '/browse/new-releases')
        payload = {'limit': limit, 'offset': offset}

        if country:
            payload['country'] = country

        return await self.request(route, params=payload)

    async def recommendations(self, seed_artists, seed_genres, seed_tracks, *, limit=20, market=None, **filters):
        route = Route('GET', '/recommendations')
        payload = {'seed_artists': seed_artists, 'seed_genres': seed_genres, 'seed_tracks': seed_tracks, 'limit': limit}

        if market:
            payload['market'] = market

        if filters:
            payload.update(filters)

        return await self.request(route, param=payload)

    async def following_artists_or_users(self, ids, *, type='artist'):
        route = Route('GET', '/me/following/contains')
        payload = {'ids': ids, 'type': type}

        return await self.request(route, params=payload)

    async def following_playlists(self, owner_id, playlist_id, *, ids):
        route = Route('GET', '/users/{owner_id}/playlists/{playlist_id}/followers/contains', owner_id=owner_id, playlist_id=playlist_id)
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def follow_artist_or_user(self, ids, *, type='artist'):
        route = Route('PUT', '/me/following')
        payload = {'ids': ids, 'type': type}

        return await self.request(route, params=payload)

    async def follow_playlist(self, owner_id, playlist_id, *, public=False):
        route = Route('PUT', '/users/{owner_id}/playlists/{playlist_id}/followers', owner_id=owner_id, playlist_id=playlist_id)

        content = json.dumps({'public': public})

        return await self.request(route, content=content)

    async def followed_artists(self, limit=20, after=None):
        route = Route('GET', '/me/following')
        payload = {'limit': limit, 'type': 'artist'}

        if after:
            payload['after'] = after

        return await self.request(route, params=payload)

    async def unfollow_artists_or_users(self, ids, *, type='artist'):
        route = Route('DELETE', '/me/following')
        payload = {'ids': ids, 'type': type}

        return await self.request(route, params=payload)

    async def unfollow_playlist(self, owner_id, playlist_id):
        route = Route('DELETE', '/users/{owner_id}/playlists/{playlist_id}/followers', owner_id=owner_id, playlist_id=playlist_id)

        return await self.request(route)

    async def is_saved_album(self, ids):
        route = Route('GET', '/me/albums/contains')
        payload = {'ids': ids}

        return await self.request(route, params=payload) 

    async def is_saved_track(self, ids):
        route = Route('GET', '/me/tracks/contains')
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def saved_albums(self, *, limit=20, offset=0, market=None):
        route = Route('GET', '/me/albums')
        payload = {'limit': limit, 'offset': offset}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def saved_tracks(self, *, limit=20, offset=0, market=None):
        route = Route('GET', '/me/tracks')
        payload = {'limit': limit, 'offset': offset}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def delete_saved_albums(self, ids):
        route = Route('DELETE', '/me/albums')
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def delete_saved_tracks(self, ids):
        route = Route('DELETE', '/me/tracks')
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def save_tracks(self, ids):
        route = Route('PUT', '/me/tracks')
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def save_albums(self, ids):
        route = Route('PUT', '/me/albums')
        payload = {'ids': ids}

        return await self.request(route, params=payload)

    async def top_artists_or_tracks(self, type, *, limit=20, offset=0, time_range=None):
        route = Route('GET', '/me/top/{type}', type=type)
        payload = {'limit': limit, 'offset': offset}

        if time_range:
            payload['time_range'] = time_range

        return await self.request(route)

    async def available_devices(self):
        route = Route('GET', '/me/player/devices')
        return await self.request(route)

    async def current_player(self, *, market=None):
        route = Route('GET', '/me/player')
        payload = {}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def recently_played(self, *, limit=20, before=None, after=None):
        route = Route('GET', '/me/player/recently-played')
        payload = {'limit': limit}

        if before:
            payload['before'] = before
        elif after:
            payload['after'] = after

        return await self.request(route, params=payload)

    async def currently_playing(self, *, market=None):
        route = Route('GET', '/me/player/currently-playing')
        payload = {}

        if market:
            payload['market'] = market
    
        return await self.request(route, params=payload)

    async def pause_playback(self, *, device_id=None):
        route = Route('PUT', '/me/player/pause')
        payload = {}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def seek_playback(self, position_ms, *, device_id=None):
        route = Route('PUT', '/me/player/repeat')
        payload = {'position_ms': position_ms}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def repeat_playback(self, state, *, device_id=None):
        route = Route('PUT', '/me/player/seek')
        payload = {'state': state}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def skip_next(self, *, device_id=None):
        route = Route('POST', '/me/player/next')
        payload = {}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def skip_previous(self, *, device_id=None):
        route = Route('POST', '/me/player/previous')
        payload = {}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def play_playback(self, context_uri, *, offset=None, device_id=None):
        route = Route('PUT', '/me/player/play')
        payload = {}

        if isinstance(context_uri, (list, tuple)):
            payload['uris'] = list(*context_uri)
        else:
            payload['context_uri'] = context_uri

        if offset:
            payload['offset'] = offset

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, data=json.dumps(payload))

    async def shuffle_playback(self, state, *, device_id=None):
        route = Route('PUT', '/me/player/seek')
        payload = {'state': state}

        if device_id:
            payload['device_id'] = device_id

        return await self.request(route, params=payload)

    async def transfer_player(self, device_id, *, play=None):
        route = Route('PUT', '/me/player')
        payload = {'device_ids': [device_id]}

        if play:
            payload['play'] = play

        return await self.request(route, data=json.dumps(payload))

    async def add_tracks_to_playlist(self, user_id, playlist_id, tracks, *, position=None):
        route = Route('POST', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        payload = {'uris': tracks}

        if position:
            payload['position'] = position

        return await self.request(route, params=payload)

    async def change_playlist_details(self, user_id, playlist_id, *, data):
        route = Route('PUT', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        return await self.request(route, data=json.dumps(data))

    async def create_playlist(self, user_id, *, data):
        route = Route('POST', '/users/{user_id}/playlists', user_id=user_id)
        return await self.request(route, data=json.dumps(data))

    async def current_playlists(self, *, limit=20, offset=0):
        route = Route('GET', '/me/playlists')
        return await self.request(route, params={'limit': limit, 'offset': offset})

    async def get_playlists(self, user_id, *, limit=20, offset=0):
        route = Route('GET', '/users/{user_id}/playlists', user_id=user_id)
        return await self.request(route, params={'limit': limit, 'offset': offset})

    async def get_playlist_cover_image(self, user_id, playlist_id):
        route = Route('GET', '/users/{user_id}/playlists/{playlist_id}/images', user_id=user_id, playlist_id=playlist_id)
        return await self.request(route)

    async def get_playlist(self, user_id, playlist_id, *, fields=None, market=None):
        route = Route('GET', '/users/{user_id}/playlists/{playlist_id}', user_id=user_id, playlist_id=playlist_id)
        payload = {}

        if fields:
            payload['fields'] = fields

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def get_playlist_tracks(self, user_id, playlist_id, *, fields=None, market=None, limit=20, offset=0):
        route = Route('GET', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        payload = {'limit': limit, 'offset':  offset}

        if fields:
            payload['fields'] = fields

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

    async def remove_tracks_from_playlist(self, user_id, playlist_id, tracks, *, position=None, snapshot_id=None):
        route = Route('DELETE ', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        payload = {'uris': tracks}

        if position:
            payload['position'] = position

        if snapshot_id:
            payload['snapshot_id'] = snapshot_id

        return await self.request(route, params=payload)

    async def reorder_playlists_tracks(self, user_id, playlist_id, range_start, range_length, insert_before, *, snapshot_id=None):
        route = Route('PUT', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        payload = {'range_start': range_start, 'range_length': range_length, 'insert_before': insert_before}

        if snapshot_id:
            payload['snapshot_id'] = snapshot_id

        return await self.request(route, data=payload)

    async def replace_playlist_tracks(self, user_id, playlist_id, uris):
        route = Route('PUT', '/users/{user_id}/playlists/{playlist_id}/tracks', user_id=user_id, playlist_id=playlist_id)
        payload = {'uris': uris}

        return await self.request(route, params=payload)

    async def upload_playlist_cover_image(self, user_id, playlist_id, file):
        route = Route('PUT', '/users/{user_id}/playlists/{playlist_id}/images', user_id=user_id, playlist_id=playlist_id)
        return await self.request(route, data=b64encode(file.read()), content_type='image/jpeg')

    async def track_audio_analysis(self, track_id):
        route = Route('GET', '/audio-analysis/{id}', id=track_id)
        return await self.request(route)

    async def track_audio_features(self, track_id):
        route = Route('GET', '/audio-features/{id}', id=track_id)
        return await self.request(route)

    async def audio_features(self, track_ids):
        route = Route('GET', '/audio-features')
        return await self.request(route, params={'ids': track_ids})

    async def track(self, track_id):
        route = Route('GET', '/tracks/{id}', id=track_id)
        return await self.request(route)

    async def tracks(self, track_ids):
        route = Route('GET', '/tracks')
        return await self.request(route, params={'ids': track_ids})

    async def current_user(self):
        route = Route('GET', '/me')
        return await self.request(route)

    async def user(self, user_id):
        route = Route('GET', '/users/{user_id}', user_id=user_id)
        return await self.request(route)

    async def search(self, q, queary_type, market='US', limit=20, offset=0):
        route = Route('GET', '/search')
        payload = {'q': q, 'type': queary_type, 'limit': limit, 'offset': offset}

        if market:
            payload['market'] = market

        return await self.request(route, params=payload)

class HTTPUserClient(HTTPClient):
    '''HTTPClient for access to user endpoints.'''
    def __init__(self, token, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self.loop)

        self.bearer_info = {'access_token': token}
        self.token = token

    async def get_bearer_info(self):
        '''for any reason if the bearer_info breaks this will restore it'''
        return {'access_token': self.token}
