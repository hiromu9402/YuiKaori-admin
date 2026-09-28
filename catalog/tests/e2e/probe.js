// 公開ページを iframe で開き、表示された結果を JSON にまとめて <pre id="result"> に出す。
// run_e2e.py が __probe.html?page=... として読み込み、Chromium の --dump-dom で結果を受け取る。
const params = new URLSearchParams(location.search);
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function waitFor(fn, timeout = 20000) {
  const start = Date.now();
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() - start > timeout) throw new Error('timeout');
    await sleep(50);
  }
}

function openPage(src) {
  return new Promise(resolve => {
    const f = document.createElement('iframe');
    f.src = src;
    f.onload = () => resolve(f.contentWindow);
    document.body.appendChild(f);
  });
}

// 表の行数が変わらなくなるまで待つ
async function stableRows(doc, selector) {
  let last = -1, same = 0;
  for (;;) {
    const n = doc.querySelectorAll(selector).length;
    if (n > 0 && n === last) { if (++same >= 4) return n; } else { same = 0; last = n; }
    await sleep(100);
  }
}

const probes = {
  async index() {
    const w = await openPage('index.html');
    const out = {};
    for (const tab of ['yui', 'kaori', 'yuikaori']) {
      w.updateSongDetails(tab);
      await sleep(300);
      await stableRows(w.document, '#songTable tr');
      out[tab] = [...w.document.querySelectorAll('#songTable tr')].map(tr => {
        const td = tr.querySelectorAll('td');
        return [td[0].textContent.trim(), td[4].textContent.trim(), td[5].textContent.trim()];
      });
    }
    return out;
  },

  async checklist() {
    const w = await openPage(params.get('target'));
    const doc = w.document;
    await waitFor(() => doc.querySelectorAll('.checkbox').length);
    await sleep(500);
    const boxes = [...doc.querySelectorAll('.checkbox')];
    // 見出し（直前の h3）と表示名を集める
    const items = boxes.map(cb => {
      let heading = null;
      for (const h of doc.querySelectorAll('h3')) {
        if (h.compareDocumentPosition(cb) & Node.DOCUMENT_POSITION_FOLLOWING) heading = h.textContent.trim();
      }
      const label = cb.closest('label') ? cb.closest('label').textContent : (cb.nextSibling ? cb.nextSibling.textContent : '');
      return { id: cb.id, heading, label: label.trim() };
    });
    await waitFor(() => { try { return w.eval('songData && setlistData'); } catch (e) { return false; } });
    const missing = {};
    for (const cb of boxes) {
      boxes.forEach(c => { c.checked = false; });
      cb.checked = true;
      cb.dispatchEvent(new Event('change'));
      const p = doc.querySelector('#searchResults p');
      missing[cb.id] = p ? p.textContent.trim() : null;
    }
    return { items, missing };
  },

  async tour() {
    const w = await openPage('tour.html');
    const doc = w.document;
    const select = await waitFor(() => {
      const s = doc.getElementById('tourSelect');
      return s && s.querySelectorAll('option[value]:not([value=""])').length ? s : null;
    });
    await sleep(300);
    const options = [...select.querySelectorAll('option')].filter(o => o.value)
      .map(o => [o.parentElement.tagName === 'OPTGROUP' ? o.parentElement.label : null, o.value, o.textContent]);
    const rows = {};
    for (const [, value] of options) {
      select.value = value;
      select.dispatchEvent(new Event('change'));
      await sleep(100);
      rows[value] = await stableRows(doc, '#concertTable tr, #setlistContainer tr');
    }
    return { options, rows };
  },

  async calendar() {
    // 出演・種類をすべて選び、出来事のない日も表示して、全日付と全イベントが出ることを確かめる
    const w = await openPage('calendar.html');
    const doc = w.document;
    await waitFor(() => doc.querySelectorAll('#list .cal-day').length);
    doc.querySelectorAll('.cal-controls input[type="checkbox"]').forEach(cb => { cb.checked = true; });
    doc.getElementById('showEmpty').dispatchEvent(new Event('change'));
    await sleep(500);
    return { rows: doc.querySelectorAll('#list .cal-day').length,
             events: doc.querySelectorAll('#list .cal-ev').length };
  },

  async event() {
    const w = await openPage('event.html');
    await stableRows(w.document, '#eventTable tr');
    await sleep(500);
    const links = [...w.document.querySelectorAll('#eventTable a')].map(a => a.getAttribute('href'));
    return { rows: w.document.querySelectorAll('#eventTable tr').length, setlistLinks: links.length,
             absoluteLinks: links.filter(h => /^https?:/.test(h)).length };
  },

  async sub() {
    const out = {};
    for (const id of ['2025112401', '2022061901', '2025051701', '2016031201']) {
      const w = await openPage(`sub/setlist.html?id=${id}`);
      await waitFor(() => w.document.querySelectorAll('#liveInfo .song').length);
      await sleep(200);
      out[`setlist:${id}`] = w.document.querySelectorAll('#liveInfo .song').length;  // 曲数（メドレーの曲も1曲ずつ）
    }
    for (const name of ['Raise', 'CUE the Future　～「Q」のテーマ～', 'Honey♥Come!!', 'winter tale']) {
      const w = await openPage(`sub/search.html?name=${encodeURIComponent(name)}`);
      await waitFor(() => /：\d+回/.test(w.document.getElementById('title').innerText));
      out[`search:${name}`] = w.document.getElementById('title').innerText.trim();
    }
    return out;
  },
};

(async () => {
  const pre = document.createElement('pre');
  pre.id = 'result';
  try {
    pre.textContent = JSON.stringify(await probes[params.get('page')]());
  } catch (e) {
    pre.textContent = JSON.stringify({ error: String(e && e.stack || e) });
  }
  document.body.appendChild(pre);
})();
