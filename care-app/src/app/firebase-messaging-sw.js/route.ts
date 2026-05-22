import { getFirebasePublicConfig, isFirebasePublicConfigured } from "@/lib/firebasePublicConfig";

export async function GET() {
  if (!isFirebasePublicConfigured()) {
    return new Response("// Firebase is not configured", {
      status: 404,
      headers: { "Content-Type": "application/javascript" },
    });
  }

  const config = getFirebasePublicConfig();
  const js = `importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js');
firebase.initializeApp(${JSON.stringify(config)});
const messaging = firebase.messaging();
messaging.onBackgroundMessage(function (payload) {
  const title = (payload.notification && payload.notification.title) || "C.A.R.E";
  const body = (payload.notification && payload.notification.body) || "";
  return self.registration.showNotification(title, {
    body: body,
    tag: (payload.data && payload.data.tag) || "care-push",
    data: { link: (payload.fcmOptions && payload.fcmOptions.link) || "/" },
  });
});
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const target = (event.notification && event.notification.data && event.notification.data.link) || '/';
  event.waitUntil(clients.openWindow(target));
});
`;

  return new Response(js, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=0, must-revalidate",
    },
  });
}
