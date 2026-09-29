export function notifyNoticeRead() {
  window.dispatchEvent(new Event('notice-read'))
}