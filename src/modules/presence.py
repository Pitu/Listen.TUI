# type: ignore
import asyncio
import os
import time

from pypresence import AioPresence, DiscordNotFound
from pypresence.exceptions import ResponseTimeout
from pypresence.payloads import Payload
from rich.pretty import pretty_repr

from src.config import Config
from src.listen.types import ListenWsData, Song
from src.module import Module
from src.modules.types import Activity, Rpc


class AioPresence(AioPresence):

    async def update(self, pid: int = os.getpid(),
                     state: str = None, details: str = None,
                     start: int = None, end: int = None,
                     large_image: str = None, large_text: str = None,
                     small_image: str = None, small_text: str = None,
                     party_id: str = None, party_size: list = None,
                     join: str = None, spectate: str = None,
                     match: str = None, buttons: list = None,
                     instance: bool = True, type: int = None):
        payload = Payload.set_activity(pid=pid, state=state, details=details, start=start, end=end,
                                       large_image=large_image, large_text=large_text,
                                       small_image=small_image, small_text=small_text, party_id=party_id,
                                       party_size=party_size, join=join, spectate=spectate,
                                       match=match, buttons=buttons, instance=instance, type=type, activity=True)
        self.send_data(1, payload)
        return await self.read_output()


class Payload(Payload):

    @classmethod
    def set_activity(cls, pid: int = os.getpid(),
                     state: str = None, details: str = None,
                     start: int = None, end: int = None,
                     large_image: str = None, large_text: str = None,
                     small_image: str = None, small_text: str = None,
                     party_id: str = None, party_size: list = None,
                     join: str = None, spectate: str = None,
                     match: str = None, buttons: list = None,
                     instance: bool = True, type: int = None,
                     activity: bool | None = True, _rn: bool = True):
        if start:
            start = int(start)
        if end:
            end = int(end)

        if activity is None:
            act_details = None
            clear = True
        else:
            act_details = {
                "state": state,
                "details": details,
                "timestamps": {
                    "start": start,
                    "end": end
                },
                "assets": {
                    "large_image": large_image,
                    "large_text": large_text,
                    "small_image": small_image,
                    "small_text": small_text
                },
                "party": {
                    "id": party_id,
                    "size": party_size
                },
                "secrets": {
                    "join": join,
                    "spectate": spectate,
                    "match": match
                },
                "buttons": buttons,
                "type": type,
                "instance": instance
            }
            clear = False

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": pid,
                "activity": act_details
            },
            "nonce": '{:.20f}'.format(cls.time())
        }
        if _rn:
            clear = _rn
        return cls(payload, clear)


class DiscordRichPresence(Module):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.presence = AioPresence(1042365983957975080)
        self.is_arrpc: bool = False
        self.config = Config.get_config()
        self._data: Rpc

    @property
    def data(self) -> Rpc | None:
        if not hasattr(self, '_data'):
            return None
        return self._data
        
    @staticmethod
    async def _get_epoch_end_time(duration: int | float | None) -> int | None:
        if not duration:
            return None
        return int(round(time.time() + duration))

    async def _sanitise(self, string: str | None) -> str:
        default: str = self.config.rpc.default_placeholder

        if len(string) < 2:
            string += default
            return string.strip()
        if len(string) >= 128:
            return f'{string[0:125]}...'.strip()
        return string.strip()
    
    async def _get_large_image(self, song: Song) -> str | None:
        use_fallback: bool = self.config.rpc.use_fallback
        fallback: str = self.config.rpc.fallback
        use_artist: bool = self.config.rpc.use_artist
        
        image = song.album_image(url=True)
        if not image and use_artist:
            image = song.artist_image(url=True)
            if not image:
                return fallback if use_fallback else None
            return image
        if not image and not use_fallback:
            return image
        return image
    
    async def _get_large_text(self, song: Song) -> str | None:
        large_text = ''
        source = song.sources_to_string()
        if source:
            large_text += f'[{source}] '
        album = song.albums_to_string()
        if album:
            large_text += album

        if len(large_text) == 0:
            return await self._sanitise(song.title)
        return await self._sanitise(large_text)

    async def _get_small_image(self, song: Song) -> str | None:
        return song.artist_image(url=True)

    async def _get_small_text(self, song: Song) -> str | None:
        return await self._sanitise(song.artists_to_string())

    async def _get_button(self) -> list[dict[str, str]]:
        return [{"label": "Join radio", "url": "https://listen.moe/"}]

    async def connect(self):
        while self._running:
            try:
                await self.presence.connect()
                self.update_status(True)
            except DiscordNotFound:
                self.update_status(True)
                # self.update_status(False, "Discord Not Found")
                self._log.info("Discord Not Found")
                await asyncio.sleep(120)
            
            while self.status.running:
                await asyncio.sleep(1)
            
    def run(self):
        self.loop.run_until_complete(self.connect())
    
    def update(self, data: ListenWsData):
        self.loop.create_task(self.aio_update(data))
    
    async def aio_update(self, data: ListenWsData | Rpc) -> None:
        if isinstance(data, ListenWsData):
            song: Song = data.song
            self._data = Rpc(
                is_arrpc=self.is_arrpc,
                detail=await self._sanitise(song.title),
                state=await self._sanitise(song.artists_to_string()),
                end=await self._get_epoch_end_time(song.duration),
                large_image=await self._get_large_image(song),
                large_text=await self._get_large_text(song),
                small_image=await self._get_small_image(song),
                small_text=await self._get_small_text(song),
                buttons=await self._get_button(),
                type=Activity.LISTENING if self.is_arrpc else Activity.PLAYING
            )
        else:
            self._data = data
        self._log.info(f'Updating presence: {pretty_repr(self.data)}')

        try:
            res = await self.presence.update(
                details=self.data.detail,
                state=self.data.state,
                end=self.data.end,
                large_image=self.data.large_image,
                large_text=self.data.large_text,
                small_image=self.data.small_image if self.data.small_image != self.data.large_image else None,
                small_text=self.data.small_text,
                buttons=self.data.buttons,
                type=self.data.type
            )
            self._log.info(f'RPC output: {pretty_repr(res)}')

            if not res.get('data', None) and not self.is_arrpc:
                self._log.info('arRPC detected')
                self.is_arrpc = True
                self.data.is_arrpc = True
                self.data.type = Activity.LISTENING
                await self.aio_update(self.data)
            elif res.get('data', None) and self.is_arrpc:
                self._log.info('Using normal discord rpc')
                self.is_arrpc = False
                self.data.is_arrpc = False
                self.data.type = Activity.PLAYING
                await self.aio_update(self.data)

        except BrokenPipeError:
            self.update_status(False, "BrokenPipeError")
            self._log.info("[RPC] BrokenPipeError")
        except (ResponseTimeout, asyncio.exceptions.CancelledError, TimeoutError):
            self.update_status(False, "RPC Response Timeout")
            self._log.info("[RPC] TimeoutError")
        except Exception as exc:
            self.update_status(False, f"{exc}")
            self._log.info("Exception has occured")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    e = DiscordRichPresence()
    e.start()

    while True:
        input()