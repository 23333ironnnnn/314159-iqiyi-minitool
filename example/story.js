const story = document.getElementById("story");
const stay = document.getElementById("stay");
const ride = document.getElementById("ride");
const again = document.getElementById("again");
const opening = story.textContent;

function show(text, atEnding) {
  story.textContent = text;
  stay.hidden = atEnding;
  ride.hidden = atEnding;
  again.hidden = !atEnding;
  (atEnding ? again : stay).focus();
}

stay.addEventListener("click", () => show("车走了。卖花的阿姨一路跑来，接过钥匙，从锁着的小推车里取出最后一束花送给你。", true));
ride.addEventListener("click", () => show("你把钥匙交给司机。他笑了，打开驾驶座旁的铁盒，翻出一张褪色的全线手绘地图。", true));
again.addEventListener("click", () => show(opening, false));
