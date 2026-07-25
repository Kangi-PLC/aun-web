# -*- coding: utf-8 -*-
"""
aun-web/index.html を aun-gas のソース（index.html + css.html + js.html）から生成する。
二重メンテ（aun-gas と aun-web に同じ変更を2回書く）を廃止するビルドスクリプト。

変換内容:
  1. <?!= include('css') ?> → css.html の中身
  2. <?!= include('js') ?>  → js.html の中身（google.script.run を fetch/gasFormPost に置換）
アンカーが1つでも見つからなければ即エラー（黙って壊れない）。

使い方: python build.py
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')

GAS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aun-gas')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')

GAS_API = 'https://script.google.com/macros/s/AKfycbzx1Q5owOLzY9shQI3-YXrHZdc5oF6_GLSJ54ypAC4tqJ5fYVB-pfUjHsMVCOxDij0/exec'

ADAPTER = """var GAS_API = '""" + GAS_API + """';

// ============================================================
// Web adapter (GitHub Pages版): hidden iframe form POST + fetch
// (bypasses CORS for GAS ANYONE_ANONYMOUS)
// ============================================================
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function gasFormPost(action, payload) {
  return new Promise(function(resolve, reject) {
    try {
      var frameName = 'gas-post-' + Date.now();
      var iframe = document.createElement('iframe');
      iframe.name = frameName;
      iframe.style.display = 'none';
      document.body.appendChild(iframe);

      var form = document.createElement('form');
      form.method = 'POST';
      form.action = GAS_API;
      form.target = frameName;
      form.style.display = 'none';

      var inpAction = document.createElement('input');
      inpAction.type = 'hidden';
      inpAction.name = 'action';
      inpAction.value = action;
      form.appendChild(inpAction);

      var inpPayload = document.createElement('input');
      inpPayload.type = 'hidden';
      inpPayload.name = 'payload';
      inpPayload.value = payload;
      form.appendChild(inpPayload);

      document.body.appendChild(form);
      form.submit();

      // Verify save by re-fetching data after POST
      setTimeout(function() {
        try { document.body.removeChild(form); } catch(ex) {}
        try { document.body.removeChild(iframe); } catch(ex) {}
        fetch(GAS_API + '?action=getData&t=' + Date.now(), { redirect: 'follow' })
          .then(function(r) { return r.text(); })
          .then(function(jsonStr) {
            try {
              var raw = JSON.parse(jsonStr);
              _lastSaveVersion = JSON.stringify(raw).length;
              resolve();
            } catch(ex) { reject(new Error('保存の確認に失敗: レスポンス不正')); }
          })
          .catch(function() { reject(new Error('保存の確認に失敗: ネットワークエラー')); });
      }, 3000);
    } catch(e) {
      reject(e);
    }
  });
}
var _lastSaveVersion = 0;
"""

# (anchor, replacement) — js.html 内の google.script.run を web 版に置換
REPLACEMENTS = [
    # doSave
    ("""  google.script.run
    .withSuccessHandler(function() { showSaveStatus('saved'); })
    .withFailureHandler(function(e) { showSaveStatus('error'); console.error(e); })
    .saveAllData(JSON.stringify(payload));""",
     """  gasFormPost('saveAllData', JSON.stringify(payload))
    .then(function() { showSaveStatus('saved'); })
    .catch(function(e) { showSaveStatus('error'); console.error(e); });"""),
    # initial load
    ("""// Load data on page open
google.script.run
  .withSuccessHandler(initApp)
  .withFailureHandler(function(e) {""",
     """// Load data on page open
fetch(GAS_API + '?action=getData', { redirect: 'follow' })
  .then(function(r) { return r.text(); })
  .then(initApp)
  .catch(function(e) {"""),
    ("""      '<button class="btn primary" style="margin-top:16px" onclick="location.reload()">再読み込み</button>';
  })
  .getData();""",
     """      '<button class="btn primary" style="margin-top:16px" onclick="location.reload()">再読み込み</button>';
  });"""),
    # startAutoReload
    ("""    google.script.run
      .withSuccessHandler(function(jsonStr) {
        var raw = JSON.parse(jsonStr);""",
     """    fetch(GAS_API + '?action=getData', { redirect: 'follow' })
      .then(function(r) { return r.text(); })
      .then(function(jsonStr) {
        var raw = JSON.parse(jsonStr);"""),
    ("""      .withFailureHandler(function(e) {
        console.log('Auto-reload failed:', e.message);
      })
      .getData();""",
     """      .catch(function(e) {
        console.log('Auto-reload failed:', e.message);
      });"""),
    # loadComments
    ("""  google.script.run
    .withSuccessHandler(function(jsonStr) {
      var comments = JSON.parse(jsonStr);
      renderComments(comments, issueId);
    })
    .withFailureHandler(function(e) {
      container.innerHTML = '<div style="color:var(--red);font-size:11px">コメント読み込みエラー</div>';
    })
    .getComments(issueId);""",
     """  fetch(GAS_API + '?action=getComments&issueId=' + encodeURIComponent(issueId), { redirect: 'follow' })
    .then(function(r) { return r.text(); })
    .then(function(jsonStr) {
      var comments = JSON.parse(jsonStr);
      renderComments(comments, issueId);
    })
    .catch(function(e) {
      container.innerHTML = '<div style="color:var(--red);font-size:11px">コメント読み込みエラー</div>';
    });"""),
    # submitComment
    ("""  google.script.run
    .withSuccessHandler(function(jsonStr) {
      // Reload comments
      loadComments(issueId);
    })
    .withFailureHandler(function(e) {
      alert('コメント送信エラー: ' + e.message);
    })
    .addComment(issueId, text, by);""",
     """  fetch(GAS_API + '?action=addComment&issueId=' + encodeURIComponent(issueId) + '&text=' + encodeURIComponent(text) + '&by=' + encodeURIComponent(by), { redirect: 'follow' })
    .then(function() { loadComments(issueId); })
    .catch(function(e) { alert('コメント送信エラー: ' + e.message); });"""),
]


def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()


def main():
    shell = read(os.path.join(GAS_DIR, 'index.html'))
    css = read(os.path.join(GAS_DIR, 'css.html'))
    js = read(os.path.join(GAS_DIR, 'js.html'))

    # js 変換
    for i, (old, new) in enumerate(REPLACEMENTS):
        if old not in js:
            raise SystemExit('ERROR: anchor %d not found in js.html — aun-gas 側の変更にビルドが追従できていない。REPLACEMENTS を更新せよ。' % i)
        js = js.replace(old, new, 1)
    if 'google.script.run' in js:
        raise SystemExit('ERROR: google.script.run が置換後も残っている。新しい呼び出しが追加された — REPLACEMENTS に追加せよ。')

    # adapter 注入（<script> 直後）
    js = js.replace('<script>', '<script>\n' + ADAPTER, 1)

    # shell へ組み込み
    if "<?!= include('css') ?>" not in shell or "<?!= include('js') ?>" not in shell:
        raise SystemExit('ERROR: include マーカーが index.html に見つからない')
    out = shell.replace("<?!= include('css') ?>", css, 1).replace("<?!= include('js') ?>", js, 1)
    out = '<!-- AUTO-GENERATED from aun-gas by build.py — 直接編集禁止。aun-gas を編集して python build.py -->\n' + out

    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(out)
    print('OK: generated %s (%d bytes)' % (OUT, len(out.encode('utf-8'))))


if __name__ == '__main__':
    main()
