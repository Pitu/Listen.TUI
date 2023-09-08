# pyright: reportUnknownMemberType=false, reportMissingTypeStubs=false
import threading
import time
from logging import DEBUG, INFO, WARN
from typing import Any, Callable

import mpv
from rich.pretty import pretty_repr

from ..config import Config
from ..modules.baseModule import BaseModule
from .types import DemuxerCacheState, MPVData

# class StreamPlayerVLC:
#     def __init__(self) -> None:
#         import vlc
#         from vlc import MediaPlayer
#         self.stream_url = "https://listen.moe/stream"
#         self.vlc = vlc.Instance()
#         self.player: MediaPlayer = self.vlc.media_player_new()
#         self.player.set_media(self.vlc.media_new(self.stream_url))
#         self.player.audio_set_volume(30)

#     def play(self) -> None:
#         self.player.play()

#     def pause(self) -> None:
#         self.player.pause()

#     def is_playing(self) -> bool:
#         return True if self.player.is_playing() else False

#     def set_volume(self, volume: int):
#         e = self.player.audio_set_volume(volume)
#         if not e:
#             return
#         else:
#             raise Exception("Unable to set volume")

#     def length(self):
#         return self.player.get_time()

#     def release(self):
#         self.player.release()

#     def retain(self):
#         self.player.retain()


class StreamPlayerMPV(BaseModule):
    def __init__(self) -> None:
        super().__init__()
        self.config = Config.get_config()
        self.stream_url = "https://listen.moe/stream"
        self.mpv_options = self.config.player.mpv_options.copy()
        self.mpv_options['volume'] = self.config.persist.last_volume
        self.player = mpv.MPV(log_handler=self._log_handler, **self.mpv_options)
        self._data: MPVData
        self.idle_count: int = 0
        self.update_able: list[Callable[[MPVData], Any]] = []

    @property
    def data(self) -> MPVData:
        return self._data

    @property
    def cache(self) -> DemuxerCacheState | None:
        cache = self._get_value('demuxer_cache_state', None)
        if not cache:
            return None
        return DemuxerCacheState.from_cache_state(cache)

    @property
    def paused(self) -> bool | None:
        return bool(self._get_value('pause'))

    @paused.setter
    def paused(self, state: bool):
        setattr(self.player, 'pause', state)

    @property
    def core_idle(self) -> bool:
        return bool(self._get_value('core_idle'))

    @property
    def volume(self) -> int:
        volume = self._get_value('volume')
        if not volume:
            return 0
        return int(volume)

    @volume.setter
    def volume(self, volume: int):
        setattr(self.player, 'volume', volume)
        self.config.update('persist', 'last_volume', volume)

    @property
    def ao_volume(self) -> float:
        ao_volume = self._get_value('ao_volume')
        if not ao_volume:
            return 0
        return float(ao_volume)

    @ao_volume.setter
    def ao_volume(self, volume: int):
        setattr(self.player, 'ao_volume', volume)

    def _log_handler(self, loglevel: str, component: str, message: str):
        match loglevel:
            case 'info':
                level = INFO
            case 'warn':
                level = WARN
            case 'debug':
                level = DEBUG
            case _:
                level = DEBUG

        if component == 'display-tags':
            return
        self._log.log(level=level, msg=f'[{component}] {message}')

    def _get_value(self, value: str, *args: Any) -> Any | None:
        try:
            return getattr(self.player, value, *args)
        except RuntimeError:
            return None

    def _restarter(self, duration: int = 20):
        self.player.wait_until_playing()
        while self._running:
            if self.core_idle and not self.paused:
                if self.idle_count > duration:
                    self._log.info(f'Idle time exceed {duration}s when not paused. Restarting...')
                    self.restart()
                    self.idle_count = 0
                self.idle_count += 1
            else:
                self.idle_count = 0
            time.sleep(1)

    def run(self):
        threading.Thread(target=self._restarter,
                         name='MPV_restarter',
                         args=(self.config.player.restart_timeout, )).start()
        self.player.play(self.stream_url)
        self.update_status(False, 'Buffering...')

        def metadata(_: Any, new_value: Any):
            if new_value:
                self._data = MPVData.from_metadata(new_value)
                self._log.debug(f'New Metadata: {pretty_repr(self._data)}')

                for method in self.update_able:
                    threading.Thread(target=method,
                                     args=(self._data,),
                                     name='metadata_updater').start()
        self.player.observe_property('metadata', metadata)
        cond: Callable[..., Any] = lambda val: True if val else False
        self.player.wait_for_property('metadata', cond=cond)
        self.player.wait_until_playing()
        self.update_status(True)
        self.player.wait_for_playback()

    def on_data_update(self, method: Callable[[MPVData], Any]):
        self.update_able.append(method)

    def restart(self):
        self.player.play(self.stream_url)
        if self.paused:
            self.play()

    def play(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def play_pause(self):
        if self.paused:
            self.play()
            self.seek_to_end()
        else:
            self.pause()

    def raise_volume(self, vol: int = 10):
        self.volume += vol

    def lower_volume(self, vol: int = 10):
        self.volume -= vol

    def seek_to_end(self):
        if self.cache:
            pause_wait = self.config.player.mpv_options.get('cache_pause_wait', None)
            if pause_wait:
                seek = self.cache.cache_duration - pause_wait
            else:
                seek = self.cache.cache_duration
        else:
            return
        self.player.seek(seek)

    def set_volume(self, volume: int):
        self.volume = volume

    def set_ao_volume(self, volume: int):
        self.ao_volume = volume


if __name__ == "__main__":
    e = StreamPlayerMPV()  # pyright: ignore
    e.start()
    while True:
        try:
            k = input()
            p = eval(k)
            print(p)
        except Exception:
            continue
