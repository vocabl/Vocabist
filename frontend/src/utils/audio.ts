import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from 'expo-audio';

let player: AudioPlayer | null = null;
let configured = false;

export async function playAudioUrl(url: string): Promise<void> {
  if (!configured) {
    try {
      await setAudioModeAsync({ playsInSilentMode: true });
    } catch {
      /* ignore */
    }
    configured = true;
  }
  if (!player) player = createAudioPlayer();
  player.replace({ uri: url });
  try {
    await player.seekTo(0);
  } catch {
    /* ignore */
  }
  player.play();
}

export function stopAudio(): void {
  try {
    player?.pause();
  } catch {
    /* ignore */
  }
}
