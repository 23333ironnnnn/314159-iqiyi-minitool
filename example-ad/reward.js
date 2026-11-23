const read = document.getElementById("read");
const statusText = document.getElementById("status");
const bonus = document.getElementById("bonus");
let pending = false;

function canRequest() {
  return window.self === window.top && window.iqiyi &&
    typeof window.iqiyi.nativeCallback === "function";
}

function updateAvailability() {
  read.hidden = !canRequest() || !bonus.hidden;
  if (!read.hidden) statusText.textContent = "故事已读完。你也可以翻开车票。";
}

document.getElementById("sdk").addEventListener("load", updateAvailability);
updateAvailability();

read.addEventListener("click", () => {
  if (pending || !bonus.hidden || !canRequest()) return;
  read.disabled = true;
  pending = true;
  statusText.textContent = "正在请求广告…";
  let settled = false;
  function finish(data) {
    if (settled) return;
    settled = true;
    pending = false;
    read.disabled = false;
    switch (data && data.code) {
      case 1001:
        bonus.hidden = false;
        read.hidden = true;
        statusText.textContent = "留言已解锁。";
        break;
      case 1002:
        statusText.textContent = "这次没有获得奖励，可以稍后再读。";
        break;
      case 1003:
        statusText.textContent = "广告加载失败，可以稍后重试。";
        break;
      default:
        statusText.textContent = "广告暂时不可用，可以稍后重试。";
    }
  }
  try {
    window.iqiyi.nativeCallback("Ad", "showRewardAdByH5Game", {}, finish);
  } catch {
    finish(null);
  }
});
