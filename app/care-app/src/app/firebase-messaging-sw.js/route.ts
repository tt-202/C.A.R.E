import {
  getFirebasePublicConfig,
  isFirebasePublicConfigured,
} from "@/lib/firebasePublicConfig";

export async function GET() {
  if (!isFirebasePublicConfigured()) {
    return new Response("// Firebase is not configured", {
      status: 404,
      headers: {
        "Content-Type": "application/javascript; charset=utf-8",
      },
    });
  }

  const config = getFirebasePublicConfig();

  const js = `
importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js');

firebase.initializeApp(${JSON.stringify(config)});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function (payload) {
  console.log('[firebase-messaging-sw.js] background message:', payload);

  const title =
    payload.notification && payload.notification.title
      ? payload.notification.title
      : 'C.A.R.E';

  const body =
    payload.notification && payload.notification.body
      ? payload.notification.body
      : '';

  const link =
    payload.data && payload.data.link
      ? payload.data.link
      : payload.fcmOptions && payload.fcmOptions.link
        ? payload.fcmOptions.link
        : '/';

  return self.registration.showNotification(title, {
    body: body,
    tag: payload.data && payload.data.tag ? payload.data.tag : 'care-push',
    icon: '/icon.png',
    badge: '/icon.png',
    data: {
      link: link,
    },
  });
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  const target =
    event.notification &&
    event.notification.data &&
    event.notification.data.link
      ? event.notification.data.link
      : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (const client of clientList) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }

      if (clients.openWindow) {
        return clients.openWindow(target);
      }
    })
  );
});
`;

  return new Response(js, {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=0, must-revalidate",
    },
  });
}
