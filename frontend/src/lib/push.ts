import { api } from "./api";
import { decode, encode } from "./crypto";

export type PushStatus = "unsupported" | "unconfigured" | "denied" | "on" | "off";

const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export async function pushStatus(publicKey: string): Promise<PushStatus> {
  if (!supported()) return "unsupported";
  if (!publicKey) return "unconfigured";
  if (Notification.permission === "denied") return "denied";
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ? "on" : "off";
}

/** Subscribe this device; notifications carry generic text only (never titles or names). */
export async function enablePush(publicKey: string): Promise<PushStatus> {
  if (await Notification.requestPermission() !== "granted") return "denied";
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true, applicationServerKey: decode(publicKey),
  });
  const json = subscription.toJSON();
  await api.subscribePush({
    endpoint: subscription.endpoint,
    p256dh: json.keys?.p256dh ?? encode(subscription.getKey("p256dh")!),
    auth: json.keys?.auth ?? encode(subscription.getKey("auth")!),
  });
  return "on";
}

export async function disablePush(): Promise<PushStatus> {
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    await api.unsubscribePush(subscription.endpoint).catch(() => {});
    await subscription.unsubscribe();
  }
  return "off";
}
