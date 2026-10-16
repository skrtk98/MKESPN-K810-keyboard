import {
    enhanceControls,
    fieldError,
    clearFieldError,
    validateFields
} from './form-controls.mjs?v=20261015-hardware';
import {
    K810,
    CONTROLS,
    KEY_GROUPS,
    CONFIG_SIZE,
    keyLabel,
    offset,
    diffSettings,
    settingsOnly,
    backupOf,
    parseBackup,
    WHEEL_ACTIONS,
    wheelLabel,
    wheelValue,
    setWheel
} from './protocol.mjs?v=20261015-hardware';
import {
    compileMacro,
    decodeMacro,
    macroKey,
    MACRO_CODES
} from './macros.mjs?v=20261015-hardware';
import {
    LIGHT_MODES,
    decodeLight,
    setLight
} from './lighting.mjs?v=20261015-hardware';
import {
    LIBRARY_KEY,
    emptyLibrary,
    parseLibrary,
    persistLibrary
} from './library.mjs?v=20261015-hardware';
import {
    recordedKey,
    MacroRecorder
} from './recording.mjs?v=20261015-hardware';

const $ = id => document.getElementById(id);
const RECOVERY_KEY = 'mkespn-k810:recovery:v1';
let session = null,
    snapshot = null,
    draft = null,
    selected = 'kp1',
    demo = false,
    busy = false,
    uncertain = false,
    recoveryDoc = null;
const keyButtons = new Map();
const KEYCAPS = {
    kp1: '1',
    kp2: '2',
    kp3: '3',
    kp4: '4',
    kp5: '5',
    kp6: '6',
    kp7: '7',
    kp8: '8',
    kp9: '9',
    kp0: '0',
    tab: 'TAB',
    enter: 'ENTER',
    left: '←',
    right: '→',
    down: '↓',
    up: '↑'
};
const pendingMacros = new Map();
let restoreImage = null;
let pendingLight = {};
let categoryKey = null,
    categoryCode = null,
    chosenCategory = null;
let selectedRow = 0;
let macroRows = [{
    type: 'key-down',
    key: 'a',
    delay: 8
}, {
    type: 'key-up',
    key: 'a',
    delay: 8
}];
const pageLinks = Array.from(document.querySelectorAll('[data-page]'));
const menu = $('mobile-navigation'),
    menuButton = $('menu-open');

function closeMenu({
    restoreFocus = true
} = {}) {
    if (menu.open) menu.close();
    menuButton.setAttribute('aria-expanded', 'false');
    if (restoreFocus) menuButton.focus();
}

function selectSettingsTab(id, {
    focus = false
} = {}) {
    if (!['keys', 'light', 'macro', 'backup', 'help'].includes(id)) id = 'keys';
    document.querySelectorAll('.settings-panel').forEach(panel => panel.hidden = panel.id !== `panel-${id}`);
    for (const link of pageLinks) {
        const active = link.dataset.page === id;
        if (active) {
            link.setAttribute('aria-current', 'page');
            link.setAttribute('data-current', '');
        } else {
            link.removeAttribute('aria-current');
            link.removeAttribute('data-current');
        }
    }
    $('mobile-page-name').textContent = pageLinks.find(link => link.dataset.page === id).textContent.trim();
    if (id !== 'macro' && recording) endRecording();
    if (focus) $(`panel-${id}`).focus();
    requestAnimationFrame(fitWorkspace);
}
for (const link of pageLinks) link.addEventListener('click', event => {
    event.preventDefault();
    const wasOpen = menu.open;
    closeMenu({
        restoreFocus: false
    });
    selectSettingsTab(link.dataset.page, {
        focus: wasOpen
    });
    history.replaceState(null, '', `#page-${link.dataset.page}`);
});
menuButton.addEventListener('click', () => {
    menuButton.setAttribute('aria-expanded', 'true');
    menu.showModal();
    $('menu-close').focus();
});
$('menu-close').addEventListener('click', () => closeMenu());
menu.addEventListener('cancel', () => {
    menuButton.setAttribute('aria-expanded', 'false');
});
menu.addEventListener('close', () => menuButton.setAttribute('aria-expanded', 'false'));
const mobileLayout = matchMedia('(max-width:700px)');
mobileLayout.addEventListener('change', event => {
    if (!event.matches) closeMenu({
        restoreFocus: false
    });
});
window.addEventListener('hashchange', () => selectSettingsTab(location.hash.replace('#page-', '')));
$('edit-key-macro').addEventListener('click', () => selectSettingsTab('macro', {
    focus: true
}));
for (const link of document.querySelectorAll('[data-wheel-direction]')) link.addEventListener('click', event => {
    event.preventDefault();
    setKeyView('wheel');
    $('wheel-settings').scrollIntoView({
        block: 'nearest'
    });
    $(`wheel-${link.dataset.wheelDirection}`).focus();
});
for (const [id, label] of CONTROLS) $('macro-key-select').add(new Option(label, id));
$('macro-key-select').addEventListener('change', () => {
    selected = $('macro-key-select').value;
    render();
});

function setKeyView(view) {
    $('workspace').dataset.view = view;
    document.querySelectorAll('[data-key-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.keyView === view)));
}
document.querySelectorAll('[data-key-view]').forEach(button => button.addEventListener('click', () => setKeyView(button.dataset.keyView)));

function showTask(kind, value) {
    document.querySelectorAll(`[data-${kind}-task]`).forEach(el => el.hidden = el.dataset[`${kind}Task`] !== value);
    if (kind === 'macro') {
        if (value !== 'record' && recording) endRecording({
            showEditor: false
        });
        $('macro-controls').hidden = value === 'library';
    }
    requestAnimationFrame(fitWorkspace);
}

function editSequence() {
    $('macro-task').value = 'sequence';
    showTask('macro', 'sequence');
}
$('light-view').addEventListener('change', () => showTask('light', $('light-view').value));
$('macro-task').addEventListener('change', () => showTask('macro', $('macro-task').value));

function showLibraryView() {
    document.querySelectorAll('[data-library-view]').forEach(el => el.hidden = el.dataset.libraryView !== $('library-view').value);
}
$('library-view').addEventListener('change', showLibraryView);
$('record-edit').addEventListener('click', editSequence);
for (const type of ['input', 'change']) $('macro-controls').addEventListener(type, event => {
    if (event.target !== $('macro-row-select')) clearFieldError($('macro-row-select'));
});
$('macro-row-select').addEventListener('change', () => {
    if (!validateFields($('macro-rows'))) {
        $('macro-row-select').value = String(selectedRow);
        return;
    }
    selectedRow = Number($('macro-row-select').value);
    renderMacroRows();
});

// When a task cannot fit, use ordinary page scrolling instead of a nested pane.
function fitWorkspace() {
    const panel = document.querySelector('.settings-panel:not([hidden])');
    if (!panel) return;
    const main = document.querySelector('main'),
        style = getComputedStyle(main);
    const fixed = ['.site-header', '.site-footer', '.review', '.desktop-navigation', '.mobile-menu-toggle', '#status']
        .map(selector => document.querySelector(selector)).filter(el => el && !el.hidden && getComputedStyle(el).display !== 'none')
        .reduce((sum, el) => sum + el.getBoundingClientRect().height, 0);
    const budget = innerHeight - fixed - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - 32;
    const panelTop = panel.getBoundingClientRect().top;
    const contentHeight = Math.max(0, ...[...panel.children].filter(el => !el.hidden && getComputedStyle(el).display !== 'none' && getComputedStyle(el).position !== 'absolute')
        .map(el => el.getBoundingClientRect().bottom - panelTop + panel.scrollTop + parseFloat(getComputedStyle(el).marginBottom || 0))) + parseFloat(getComputedStyle(panel).paddingBottom);
    document.documentElement.classList.toggle('document-flow', contentHeight > budget + 2);
}
const fitObserver = new ResizeObserver(() => requestAnimationFrame(fitWorkspace));
for (const el of document.querySelectorAll('.settings-panel,.site-header,.review,.site-footer,#status')) fitObserver.observe(el);
window.addEventListener('resize', fitWorkspace);

function changesNow() {
    if (!snapshot) return [];
    const changes = diffSettings(snapshot.data, draft).filter(c => !pendingMacros.has(c.id));
    for (const [id, spec] of pendingMacros) changes.push({
        kind: 'macro',
        id,
        label: CONTROLS.find(c => c[0] === id)[1],
        before: keyLabel(snapshot.data[offset(id)]),
        after: `マクロ（${spec.events.length}行）`
    });
    if (restoreImage) changes.push({
        kind: 'macro',
        label: '保存済みマクロ領域',
        before: '本体の設定',
        after: '完全バックアップから復元'
    });
    if (Object.keys(pendingLight).length) {
        const after = setLight(snapshot.data, pendingLight);
        if (!after.every((v, i) => v === snapshot.data[i])) changes.push({
            kind: 'light',
            label: '照明',
            before: lightSummary(snapshot.data),
            after: lightSummary(after)
        });
    }
    return changes;
}


function message(text, type = 'info', title) {
    const banner = $('status'),
        error = type === 'error',
        success = type === 'success',
        warning = type === 'warning';
    // Blocking failures have one presentation. Field errors use fieldError instead.
    if (error) {
        banner.hidden = true;
        $('result-dialog-title').textContent = title ?? '操作を完了できませんでした';
        $('result-dialog-text').textContent = text;
        if (!$('result-dialog').open) $('result-dialog').showModal();
        $('result-dialog-title').focus();
        return;
    }
    banner.dataset.type = success ? 'success' : warning ? 'warning' : 'info-1';
    banner.setAttribute('role', warning ? 'alert' : 'status');
    banner.setAttribute('aria-live', warning ? 'assertive' : 'polite');
    $('status-title').textContent = title ?? (success ? '完了しました' : busy ? '処理中' : 'お知らせ');
    $('status-text').textContent = text;
    banner.hidden = false;
    const icon = banner.querySelector('.dads-notification-banner__icon');
    icon.replaceChildren();
    const shape = document.createElementNS('http://www.w3.org/2000/svg', warning ? 'path' : 'circle');
    if (warning) shape.setAttribute('d', 'M1 21 12 2l11 19H1Z');
    else {
        shape.setAttribute('cx', '12');
        shape.setAttribute('cy', '12');
        shape.setAttribute('r', '10');
    }
    shape.setAttribute('fill', 'currentColor');
    icon.append(shape);
    const mark = document.createElementNS(icon.namespaceURI, 'path');
    mark.setAttribute('fill', 'Canvas');
    mark.setAttribute('d', warning ? 'M11 10h2v5h-2zm0 6h2v2h-2z' : success ? 'm17.6 9.6-7 7-4.3-4.3L7.7 11l2.9 2.9 5.7-5.6 1.3 1.4Z' : 'M11 10h2v7h-2zm0-4h2v2h-2z');
    icon.append(mark);
}
$('status-close').addEventListener('click', () => {
    $('status').hidden = true;
    (mobileLayout.matches ? $('menu-open') : document.querySelector('.desktop-navigation [aria-current]'))?.focus();
});
for (const id of ['result-dialog-close', 'result-dialog-ok']) $(id).addEventListener('click', () => $('result-dialog').close());

function renderKeyChoices(hasData) {
    const code = hasData ? draft[offset(selected)] : null;
    if (categoryKey !== selected || categoryCode !== code || chosenCategory === null) {
        categoryKey = selected;
        categoryCode = code;
        chosenCategory = String(KEY_GROUPS.findIndex(([, keys]) => keys.some(([value]) => value === code)));
        if (chosenCategory === '-1') chosenCategory = hasData ? 'current' : '0';
    }
    const category = $('key-category'),
        choice = $('key-select');
    category.replaceChildren();
    KEY_GROUPS.forEach(([label], i) => category.add(new Option(label, String(i))));
    if (code !== null && !KEY_GROUPS.some(([, keys]) => keys.some(([value]) => value === code))) category.add(new Option('現在の特殊割り当て', 'current'));
    category.value = chosenCategory;
    choice.replaceChildren();
    const keys = chosenCategory === 'current' ? [
        [code, keyLabel(code)]
    ] : KEY_GROUPS[Number(chosenCategory)][1];
    if (!keys.some(([value]) => value === code)) {
        const placeholder = new Option('選択してください', '', true, true);
        placeholder.disabled = true;
        choice.add(placeholder);
    }
    keys.forEach(([value, label]) => choice.add(new Option(label, String(value))));
    if (keys.some(([value]) => value === code)) choice.value = String(code);
    category.disabled = busy || !hasData || uncertain;
    choice.disabled = busy || !hasData || uncertain;
}
$('key-category').addEventListener('change', () => {
    chosenCategory = $('key-category').value;
    renderKeyChoices(!!snapshot);
});

function render() {
    const hasData = !!snapshot,
        changes = changesNow();
    renderLight(hasData);
    $('library-controls').disabled = busy;
    $('library-group').disabled = busy;
    $('status-close').disabled = busy;
    for (const [id, label] of CONTROLS) {
        const button = keyButtons.get(id),
            code = hasData ? draft[offset(id)] : null;
        const printed = KEYCAPS[id];
        const stored = hasData ? keyLabel(snapshot.data[offset(id)]) : '未読み取り';
        const changed = hasData && (pendingMacros.has(id) || code !== snapshot.data[offset(id)]);
        const proposed = pendingMacros.has(id) ? 'マクロ' : code === null ? '未読み取り' : keyLabel(code);
        button.querySelector('.key-name').textContent = printed;
        button.setAttribute('aria-pressed', String(selected === id));
        button.title = `${printed}（${label}）\n割り当て：${stored}${changed?`\n変更後（未保存）：${proposed}`:''}`;
        button.setAttribute('aria-label', `${label}、印字 ${printed}、割り当て ${stored}${changed?`、変更後 ${proposed}（未保存）`:''}`);
        button.classList.toggle('changed', changed);
        button.disabled = busy;
    }
    $('editor-title').textContent = CONTROLS.find(c => c[0] === selected)[1];
    $('macro-key-select').value = selected;
    $('macro-key-select').disabled = busy;
    $('macro-controls').disabled = busy || !hasData || uncertain;
    $('read-macro').disabled = busy || !session || uncertain || !MACRO_CODES.includes(snapshot?.data[offset(selected)]);
    $('current-key').textContent = hasData ? keyLabel(snapshot.data[offset(selected)]) : '未読み取り';
    $('current-key').closest('.current').hidden = !hasData || (!pendingMacros.has(selected) && draft[offset(selected)] === snapshot.data[offset(selected)]);
    renderKeyChoices(hasData);
    for (const direction of ['up', 'down']) {
        const select = $(`wheel-${direction}`);
        select.querySelectorAll('[data-extra]').forEach(o => o.remove());
        if (hasData) {
            const value = wheelValue(draft, direction);
            if (!WHEEL_ACTIONS.some(a => a[0] === value)) {
                const option = new Option(wheelLabel(value), String(value));
                option.dataset.extra = 'true';
                select.add(option);
            }
            select.value = String(value);
        }
        select.disabled = busy || !hasData || uncertain;
        $(`wheel-current-${direction}`).textContent = hasData ? wheelLabel(wheelValue(snapshot.data, direction)) : '未読み取り';
        $(`wheel-current-${direction}`).closest('p').hidden = !hasData || wheelValue(snapshot.data, direction) === wheelValue(draft, direction);
        const printed = direction === 'up' ? '↑' : '↓',
            directionName = direction === 'up' ? '上方向' : '下方向';
        const stored = hasData ? wheelLabel(wheelValue(snapshot.data, direction)) : '未読み取り';
        const changed = hasData && wheelValue(snapshot.data, direction) !== wheelValue(draft, direction);
        const proposed = hasData ? wheelLabel(wheelValue(draft, direction)) : '未読み取り';
        const preview = $(`wheel-${direction}-preview`);
        preview.title = `ホイール ${printed}（${directionName}）\n割り当て：${stored}${changed?`\n変更後（未保存）：${proposed}`:''}`;
        preview.setAttribute('aria-label', `ホイール${directionName}の設定へ移動、割り当て ${stored}${changed?`、変更後 ${proposed}（未保存）`:''}`);
    }
    $('wheel-swap').disabled = busy || !hasData || uncertain || ['up', 'down'].some(d => !WHEEL_ACTIONS.some(a => a[0] === wheelValue(draft, d)));
    $('revert-key').disabled = busy || !hasData || (!pendingMacros.has(selected) && draft[offset(selected)] === snapshot?.data[offset(selected)]);
    $('revert-key').hidden = $('current-key').closest('.current').hidden;
    $('apply').disabled = busy || demo || !session || !changes.length || uncertain;
    $('reset').disabled = busy || !changes.length;
    $('reload').disabled = busy || !session;
    $('export').disabled = busy || !hasData || demo || uncertain;
    $('import').disabled = busy || !hasData || demo || uncertain;
    $('recovery').disabled = busy || !recoveryDoc;
    $('connect').disabled = busy || !!session || !('hid' in navigator) || !window.isSecureContext;
    $('demo').disabled = busy || !!session;
    $('disconnect').hidden = !session;
    $('disconnect').disabled = busy;
    $('workspace').setAttribute('aria-busy', String(busy));
    $('change-count').textContent = changes.length ? `${changes.length}件の変更` : '変更なし';
    $('no-changes').hidden = changes.length > 0;
    $('changes').replaceChildren(...changes.map(change => {
        const li = document.createElement('li');
        const label = ['macro', 'light'].includes(change.kind) ? v => v : change.kind === 'wheel' ? wheelLabel : keyLabel;
        for (const [tag, text] of [
                ['span', change.label],
                ['span', label(change.before)],
                ['span', '→'],
                ['strong', label(change.after)]
            ]) {
            const item = document.createElement(tag);
            item.textContent = text;
            li.append(item);
        }
        return li;
    }));
}
async function run(action, {
    writing = false
} = {}) {
    if (busy) return;
    busy = true;
    render();
    try {
        await action();
    } catch (error) {
        if (writing) uncertain = true;
        if (error.name === 'NotFoundError') message('機器の選択がキャンセルされました。');
        else message(`${error.message}${writing?' 保存前の復元データを取得し、本体から再読み取りしてください。':''}`, 'error');
    } finally {
        busy = false;
        render();
    }
}
async function usbLock(action) {
    if (!navigator.locks) throw new Error('このブラウザの排他制御に対応していません。PC版ChromeまたはEdgeを使用してください。');
    return navigator.locks.request('mkespn-k810-usb', {
        ifAvailable: true
    }, lock => {
        if (!lock) throw new Error('別のタブが通信中です。処理が終わってからお試しください。');
        return action();
    });
}

function download(doc, name) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], {
        type: 'application/json'
    }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function setSnapshot(value) {
    chosenCategory = null;
    snapshot = value;
    draft = value.data.slice();
    uncertain = false;
    pendingMacros.clear();
    restoreImage = null;
    pendingLight = {};
}
async function reload() {
    message('本体の設定を読み取っています…');
    setSnapshot(await usbLock(() => session.exclusive(() => session.snapshot())));
    message('現在の設定を読み取りました。キーを選んで編集できます。', 'success');
}

for (const [id, label] of CONTROLS) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `key ${id}`;
    button.setAttribute('aria-pressed', 'false');
    const name = document.createElement('span');
    name.className = 'key-name';
    name.textContent = KEYCAPS[id];
    const position = document.createElement('span');
    position.className = 'key-position';
    position.textContent = label;
    button.append(name, position);
    if (id === 'enter') {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'enter-shape');
        svg.setAttribute('viewBox', '0 0 100 100');
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS(svg.namespaceURI, 'path');
        path.setAttribute('d', 'M7 1 H93 Q99 1 99 7 V93 Q99 99 93 99 H22 Q16 99 16 93 V51 Q16 48 13 48 H7 Q1 48 1 42 V7 Q1 1 7 1 Z');
        path.setAttribute('vector-effect', 'non-scaling-stroke');
        svg.append(path);
        button.prepend(svg);
    }
    button.addEventListener('click', () => {
        selected = id;
        render();
        setKeyView('key');
    });
    (CONTROLS.findIndex(c => c[0] === id) < 12 ? $('keypad') : $('stick')).append(button);
    keyButtons.set(id, button);
}
for (const direction of ['up', 'down']) {
    const select = $(`wheel-${direction}`);
    for (const [code, label] of WHEEL_ACTIONS) select.add(new Option(label, String(code)));
    select.addEventListener('change', () => {
        if (!busy && draft) {
            draft = setWheel(draft, direction, Number(select.value));
            render();
        }
    });
}
$('wheel-swap').addEventListener('click', () => {
    const up = wheelValue(draft, 'up'),
        down = wheelValue(draft, 'down');
    draft = setWheel(setWheel(draft, 'up', down), 'down', up);
    render();
});
$('key-select').addEventListener('change', () => {
    if (!busy && draft) {
        pendingMacros.delete(selected);
        draft[offset(selected)] = Number($('key-select').value);
        render();
    }
});
$('revert-key').addEventListener('click', () => {
    pendingMacros.delete(selected);
    draft[offset(selected)] = snapshot.data[offset(selected)];
    render();
});
$('reset').addEventListener('click', () => {
    pendingMacros.clear();
    restoreImage = null;
    pendingLight = {};
    draft = snapshot.data.slice();
    render();
    message('未保存の変更をすべて取り消しました。');
});
$('connect').addEventListener('click', () => run(async () => {
    let devices = (await navigator.hid.getDevices()).filter(d => K810.matches(d));
    if (devices.length !== 1) devices = await navigator.hid.requestDevice({
        filters: [{
            vendorId: 0x30fa,
            productId: 0x2350,
            usagePage: 0xff01,
            usage: 1
        }]
    });
    const device = devices.find(d => K810.matches(d));
    if (!device) throw new Error('対応するK810が選択されていません。');
    const candidate = new K810(device, {
        progress: (done, total) => message(`本体の設定を読み取っています… ${Math.round(done/total*100)}%`)
    });
    try {
        await candidate.open();
        const value = await usbLock(() => candidate.exclusive(() => candidate.snapshot()));
        session = candidate;
        demo = false;
        setSnapshot(value);
        $('device-status').replaceChildren();
        const dot = document.createElement('span');
        dot.className = 'status-dot';
        $('device-status').append(dot, '接続済み · USB Keyboard（30FA:2350）');
        $('device-status').className = 'connected';
        message('本体の設定を読み取りました。編集後に保存すると、本体の割り当てが変わります。', 'success', '接続しました');
    } catch (error) {
        if (device.opened) await device.close();
        throw error;
    }
}));
$('disconnect').addEventListener('click', () => run(async () => {
    await session.finishConfiguration();
    await session.device.close();
    session = null;
    snapshot = null;
    draft = null;
    demo = false;
    uncertain = false;
    $('device-status').textContent = '未接続';
    $('device-status').className = '';
    message('キーボードとの接続を終了しました。');
}));
$('demo').addEventListener('click', () => {
    if (busy || session) return;
    demo = true;
    const data = new Uint8Array(CONFIG_SIZE).fill(255);
    data[0x20] = 0x10;
    data.set(setLight(data, {
        mode: 'breathing',
        brightness: 6,
        speed: 3,
        direction: 0,
        symmetry: false,
        color_selection: 0,
        colors_enabled: 127,
        reaction_type: 0,
        colors: [
            [15, 15, 255],
            [255, 15, 15],
            [15, 255, 15],
            [15, 255, 255],
            [255, 255, 15],
            [255, 15, 255],
            [255, 255, 255]
        ]
    }));
    const codes = [20, 26, 8, 21, 41, 4, 22, 7, 40, 43, 44, 6, 80, 79, 81, 82];
    CONTROLS.forEach(([id], i) => data[offset(id)] = codes[i]);
    setSnapshot({
        base: 0xe0,
        header: Uint8Array.of(0xe1, 0x1e, 0xe0, 0, 0xf0, 0x0f, 0, 0),
        data
    });
    message('デモモードです。自由に編集できます。本体への通信・書き込みは行いません。');
    render();
});
$('reload').addEventListener('click', () => run(reload));
$('apply').addEventListener('click', () => run(async () => {
    if (!session || demo || uncertain) throw new Error('本体へ接続し直してください。');
    message('設定を確認して保存しています。USBを抜かずにお待ちください…');
    const saveRecovery = async doc => {
        localStorage.setItem(RECOVERY_KEY, JSON.stringify(doc));
        recoveryDoc = doc;
    };
    const result = await usbLock(() => pendingMacros.size || restoreImage ?
        session.applyExtended(snapshot, draft, pendingMacros, restoreImage, saveRecovery, pendingLight) : session.apply(snapshot, draft, saveRecovery, pendingLight));
    setSnapshot(result);
    message('読み戻しが一致しました。実際に操作して動作を確認してください。', 'success', '設定を保存しました');
}, {
    writing: true
}));
$('export').addEventListener('click', () => run(async () => {
    message('マクロを含む完全バックアップを読み取っています…');
    const value = await usbLock(() => session.exclusive(() => session.fullSnapshot()));
    download(await backupOf(value), `k810-${new Date().toISOString().replace(/[:.]/g,'-')}.json`);
    message('完全バックアップを保存しました。', 'success');
}));
$('recovery').addEventListener('click', () => {
    if (recoveryDoc) download(recoveryDoc, 'k810-before-save.json');
});
$('import').addEventListener('click', () => $('backup-file').click());
$('backup-file').addEventListener('change', () => run(async () => {
    const file = $('backup-file').files[0];
    $('backup-file').value = '';
    if (!file) return;
    if (file.size > 65536) throw new Error('バックアップファイルが大きすぎます。');
    const value = await parseBackup(JSON.parse(await file.text()));
    if (value.base !== snapshot.base) throw new Error('本体とバックアップの設定位置が一致しません。');
    if (!value.image && CONTROLS.some(([id]) => MACRO_CODES.includes(value.data[offset(id)]) && value.data[offset(id)] !== snapshot.data[offset(id)])) throw new Error('マクロの復元には完全バックアップが必要です。');
    pendingMacros.clear();
    restoreImage = value.image ?? null;
    pendingLight = {};
    draft = settingsOnly(snapshot.data, value.data);
    message('復元内容を読み込みました。変更一覧を確認し、「キーボードに保存する」で適用してください。');
}));
window.addEventListener('beforeunload', event => {
    if (busy || changesNow().length) {
        event.preventDefault();
        event.returnValue = '';
    }
});
navigator.hid?.addEventListener('disconnect', event => {
    if (event.device !== session?.device) return;
    session = null;
    uncertain = true;
    $('device-status').textContent = 'USB接続が切れました';
    $('device-status').className = '';
    message('USB接続が切れました。復元データを取得できます。再接続して本体の状態を確認してください。', 'error');
    render();
});

function lightSummary(data) {
    const v = decodeLight(data),
        mode = LIGHT_MODES.find(m => m[0] === v.mode)?.[1] ?? `モード${v.mode_code}`;
    const colors = v.colors.map(rgb => '#' + rgb.map(c => c.toString(16).padStart(2, '0')).join('')).join('・');
    return `${mode}／明るさ${v.brightness}／速度${v.speed}／方向${v.direction+1}／${v.symmetry?'対称':'非対称'}／色${v.color_selection||'循環'}／反応${v.reaction_type+1}／循環対象${v.colors_enabled.toString(2).padStart(7,'0')}／${colors}`;
}

function renderLight(hasData) {
    $('light-controls').disabled = busy || !hasData || uncertain;
    $('revert-light').disabled = busy || !Object.keys(pendingLight).length;
    $('light-current').textContent = hasData ? `本体：${lightSummary(snapshot.data)}` : '未読み取り';
    if (!hasData) return;
    const v = decodeLight(setLight(snapshot.data, pendingLight));
    $('light-mode').querySelectorAll('[data-extra]').forEach(o => o.remove());
    if (v.mode === 'unknown') {
        const o = new Option(`未対応のモード（${v.mode_code}）`, 'unknown');
        o.dataset.extra = 'true';
        $('light-mode').add(o);
    }
    $('light-mode').value = v.mode;
    for (const [id, key] of [
            ['light-brightness', 'brightness'],
            ['light-speed', 'speed'],
            ['light-direction', 'direction'],
            ['light-reaction', 'reaction_type'],
            ['light-color', 'color_selection']
        ]) $(id).value = String(v[key]);
    $('light-symmetry').checked = v.symmetry;
    v.colors.forEach((rgb, i) => {
        $(`light-rgb-${i}`).value = '#' + rgb.map(c => c.toString(16).padStart(2, '0')).join('');
        $(`light-enabled-${i}`).checked = !!(v.colors_enabled & (1 << i));
    });
}
for (const [id, label] of LIGHT_MODES) $('light-mode').add(new Option(label, id));
for (let i = 0; i < 7; i++) {
    $('light-color').add(new Option(`色${i+1}だけを使用`, String(i + 1)));
    const item = document.createElement('div');
    item.className = 'palette-item';
    const label = document.createElement('label');
    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.id = `light-enabled-${i}`;
    enabled.setAttribute('aria-label', `色${i+1}を循環に含める`);
    const color = document.createElement('input');
    color.type = 'color';
    color.id = `light-rgb-${i}`;
    color.setAttribute('aria-label', `色${i+1}のRGB`);
    label.append(enabled, `色${i+1}`);
    item.append(label, color);
    $('light-palette').append(item);
}
$('stage-light').addEventListener('click', () => {
    if (busy || !snapshot || uncertain) return;
    if (!validateFields($('light-controls'))) return;
    try {
        const fields = {
            mode: $('light-mode').value,
            brightness: Number($('light-brightness').value),
            speed: Number($('light-speed').value),
            direction: Number($('light-direction').value),
            reaction_type: Number($('light-reaction').value),
            color_selection: Number($('light-color').value),
            symmetry: $('light-symmetry').checked,
            colors_enabled: Array.from({
                length: 7
            }, (_, i) => $(`light-enabled-${i}`).checked ? 1 << i : 0).reduce((a, b) => a | b, 0),
            colors: Array.from({
                length: 7
            }, (_, i) => $(`light-rgb-${i}`).value.slice(1).match(/../g).map(s => parseInt(s, 16)))
        };
        setLight(snapshot.data, fields);
        pendingLight = fields;
        render();
        message('照明設定を変更一覧に追加しました。保存すると本体に反映されます。');
    } catch (e) {
        $('light-view').value = 'colors';
        showTask('light', 'colors');
        fieldError($('light-color'), e.message);
    }
});
$('revert-light').addEventListener('click', () => {
    pendingLight = {};
    render();
    message('照明の未保存変更を取り消しました。');
});

let library = emptyLibrary();
try {
    const stored = localStorage.getItem(LIBRARY_KEY);
    if (stored) library = parseLibrary(JSON.parse(stored));
} catch {
    message('保存済みライブラリを読み込めませんでした。元データは保持しています。', 'error');
}

function selectedGroup() {
    return library.groups.find(g => g.id === $('library-group').value);
}

function selectedMacro() {
    return selectedGroup()?.macros.find(m => m.id === $('library-macro').value);
}

function renderLibrary(groupId = $('library-group').value, macroId = $('library-macro').value) {
    $('library-group').replaceChildren(...library.groups.map(g => new Option(g.name, g.id)));
    if (library.groups.some(g => g.id === groupId)) $('library-group').value = groupId;
    const group = selectedGroup();
    $('library-group-name').value = group?.name ?? 'マイマクロ';
    $('library-macro').replaceChildren(...(group?.macros ?? []).map(m => new Option(m.name, m.id)));
    if (group?.macros.some(m => m.id === macroId)) $('library-macro').value = macroId;
    const macro = selectedMacro();
    $('library-macro-name').value = macro?.name ?? '新しいマクロ';
    for (const id of ['library-group-rename', 'library-group-delete', 'library-save-new']) $(id).disabled = !group;
    for (const id of ['library-load', 'library-update', 'library-delete']) $(id).disabled = !macro;
}

function changeLibrary(action, nameField) {
    if (nameField && !$(nameField).value.trim()) {
        fieldError($(nameField), '名前を入力してください。');
        return;
    }
    try {
        const draft = structuredClone(library),
            selection = action(draft) ?? {};
        library = persistLibrary(localStorage, draft);
        renderLibrary(selection.group, selection.macro);
        message('このブラウザに保存しました。本体の設定は変わりません。', 'success', 'ライブラリを保存しました');
    } catch (error) {
        if (error.editorInvalid) {
            editSequence();
            if (validateFields($('macro-controls'))) fieldError($('macro-row-select'), error.message);
            return;
        }
        message(`ライブラリを保存できませんでした：${error.message}`, 'error');
    }
}
const editorSpec = () => ({
    mode: $('macro-mode').value,
    repeat: Number($('macro-repeat').value),
    events: structuredClone(macroRows)
});
$('library-group').addEventListener('change', () => renderLibrary());
$('library-macro').addEventListener('change', () => {
    $('library-macro-name').value = selectedMacro()?.name ?? '';
});
$('library-group-new').addEventListener('click', () => changeLibrary(draft => {
    const group = {
        id: crypto.randomUUID(),
        name: $('library-group-name').value,
        macros: []
    };
    draft.groups.push(group);
    return {
        group: group.id
    };
}, 'library-group-name'));
$('library-group-rename').addEventListener('click', () => changeLibrary(draft => {
    draft.groups.find(g => g.id === selectedGroup().id).name = $('library-group-name').value;
}, 'library-group-name'));
$('library-group-delete').addEventListener('click', () => changeLibrary(draft => {
    draft.groups = draft.groups.filter(g => g.id !== selectedGroup().id);
}));
for (const [id, update] of [
        ['library-save-new', false],
        ['library-update', true]
    ]) $(id).addEventListener('click', () => changeLibrary(draft => {
    const group = draft.groups.find(g => g.id === selectedGroup().id),
        macro = {
            id: update ? selectedMacro().id : crypto.randomUUID(),
            name: $('library-macro-name').value,
            spec: editorSpec()
        };
    try {
        compileMacro(macro.spec);
    } catch (error) {
        error.editorInvalid = true;
        throw error;
    }
    if (update) group.macros[group.macros.findIndex(m => m.id === macro.id)] = macro;
    else group.macros.push(macro);
    return {
        group: group.id,
        macro: macro.id
    };
}, 'library-macro-name'));
$('library-delete').addEventListener('click', () => changeLibrary(draft => {
    const group = draft.groups.find(g => g.id === selectedGroup().id);
    group.macros = group.macros.filter(m => m.id !== selectedMacro().id);
}));
$('library-load').addEventListener('click', () => {
    if (busy) return;
    const macro = selectedMacro();
    if (!macro) return;
    selectedRow = 0;
    editSequence();
    macroRows = structuredClone(macro.spec.events);
    $('macro-mode').value = macro.spec.mode ?? 'repeat';
    $('macro-repeat').value = String(macro.spec.repeat ?? 1);
    renderMacroRows();
    message(`「${macro.name}」を編集画面へ読み込みました。「変更に追加」で対象キーに割り当てられます。`);
});
$('library-export').addEventListener('click', () => download(parseLibrary(library), 'k810-macro-library.json'));
$('library-import').addEventListener('click', () => $('library-file').click());
$('library-file').addEventListener('change', async () => {
    const file = $('library-file').files[0];
    $('library-file').value = '';
    if (!file || busy) return;
    try {
        if (file.size > 1048576) throw new Error('ライブラリファイルは1MiBまでです。');
        const imported = parseLibrary(JSON.parse(await file.text()));
        changeLibrary(draft => {
            for (const group of imported.groups) draft.groups.push({
                ...group,
                id: crypto.randomUUID(),
                macros: group.macros.map(m => ({
                    ...m,
                    id: crypto.randomUUID()
                }))
            });
        });
    } catch (error) {
        message(error.message, 'error');
    }
});
renderLibrary();

function stage(spec) {
    if (busy || !snapshot || uncertain) return;
    try {
        compileMacro(spec);
        pendingMacros.set(selected, structuredClone(spec));
        message(`${CONTROLS.find(c=>c[0]===selected)[1]}のマクロを変更一覧に追加しました。保存すると本体に反映されます。`, 'success');
        render();
    } catch (error) {
        message(error.message, 'error');
    }
}
$('stage-shortcut').addEventListener('click', () => {
    try {
        const keys = $('shortcut-input').value.split('+').map(k => macroKey(k.trim()));
        const spec = {
            events: [...keys.map(key => ({
                type: 'key-down',
                key
            })), ...keys.toReversed().map(key => ({
                type: 'key-up',
                key
            }))]
        };
        compileMacro(spec);
        stage(spec);
    } catch (error) {
        fieldError($('shortcut-input'), error.message);
    }
});
$('stage-mouse').addEventListener('click', () => {
    const action = $('mouse-action').value;
    stage({
        events: action.startsWith('scroll-') ? [{
            type: 'scroll',
            steps: action === 'scroll-up' ? 1 : -1
        }] : [{
            type: 'mouse-down',
            button: action
        }, {
            type: 'mouse-up',
            button: action
        }]
    });
});
const sequenceSteps = new WeakMap();

function renderMacroRows() {
    const container = $('macro-rows');
    const hadFocus = container.contains(document.activeElement);
    const focusLabel = hadFocus ? document.activeElement.getAttribute('aria-label') : null;
    container.replaceChildren();
    selectedRow = Math.max(0, Math.min(selectedRow, macroRows.length - 1));
    $('macro-row-select').replaceChildren(...macroRows.map((event, i) => new Option(`${i+1} / ${macroRows.length} · ${{'key-down':'キーを押す','key-up':'キーを離す','mouse-down':'マウスを押す','mouse-up':'マウスを離す',scroll:'スクロール',move:'移動',led:'照明',delay:'待機'}[event.type]}`, String(i))));
    $('macro-row-select').value = String(selectedRow);
    $('macro-row-select').disabled = !macroRows.length;
    macroRows.forEach((event, i) => {
        if (i !== selectedRow) return;
        const row = document.createElement('div');
        row.className = 'macro-row';
        const heading = document.createElement('h4');
        heading.textContent = `操作 ${i+1}`;
        row.append(heading);
        const field = (name, control) => {
            const label = document.createElement('label');
            label.textContent = name;
            control.setAttribute('aria-label', `${i+1}行目 ${name}`);
            label.append(control);
            row.append(label);
            return control;
        };
        const type = document.createElement('select');
        type.className = 'dads-select__select';
        type.dataset.size = 'md';
        for (const [value, label] of [
                ['key-down', 'キーを押す'],
                ['key-up', 'キーを離す'],
                ['mouse-down', 'マウスを押す'],
                ['mouse-up', 'マウスを離す'],
                ['scroll', 'スクロール'],
                ['move', 'ポインター移動'],
                ['led', '照明シーケンス'],
                ['delay', '待機']
            ]) type.add(new Option(label, value));
        type.value = event.type;
        type.addEventListener('change', () => {
            macroRows[i] = {
                type: type.value,
                key: 'a',
                button: 'left',
                steps: 1,
                x: 0,
                y: 0,
                delay: event.delay ?? 8,
                ...(type.value === 'led' ? {
                    behavior: 0,
                    sequence: [{
                        mode: 'constant',
                        color: 1,
                        duration_ms: 1000
                    }]
                } : {})
            };
            renderMacroRows();
        });
        field('操作', type);
        if (event.type.startsWith('key-')) {
            const select = document.createElement('select');
            select.className = 'dads-select__select';
            select.dataset.size = 'md';
            for (const [name, keys] of KEY_GROUPS) {
                const group = document.createElement('optgroup');
                group.label = name;
                for (const [code, label] of keys)
                    if ((code >= 4 && code <= 0xa4) || (code >= 0xe0 && code <= 0xe7)) group.append(new Option(label, `0x${code.toString(16)}`));
                if (group.children.length) select.append(group);
            }
            select.value = `0x${macroKey(event.key).toString(16)}`;
            select.addEventListener('change', () => event.key = select.value);
            field('キー', select);
        } else if (event.type.startsWith('mouse-')) {
            const select = document.createElement('select');
            select.className = 'dads-select__select';
            select.dataset.size = 'md';
            for (const [value, label] of [
                    ['left', '左ボタン'],
                    ['right', '右ボタン'],
                    ['middle', '中ボタン']
                ]) select.add(new Option(label, value));
            select.value = event.button;
            select.addEventListener('change', () => event.button = select.value);
            field('ボタン', select);
        }
        for (const [property, label, min, max] of event.type === 'scroll' ? [
                ['steps', 'スクロール量（上が＋）', -127, 127]
            ] : event.type === 'move' ? [
                ['x', '横移動量（右が＋）', -32767, 32767],
                ['y', '縦移動量（下が＋）', -32767, 32767]
            ] : []) {
            const input = document.createElement('input');
            input.type = 'number';
            input.min = String(min);
            input.max = String(max);
            input.value = String(event[property]);
            input.addEventListener('input', () => event[property] = Number(input.value));
            field(label, input);
        }
        if (event.type === 'led') {
            const sequence = document.createElement('fieldset');
            sequence.className = 'led-sequence';
            const legend = document.createElement('legend');
            legend.textContent = `${i+1}行目の照明（本体の7色を使用）`;
            sequence.append(legend);
            if (event.behavior) {
                const note = document.createElement('p');
                note.textContent = `実行方式${event.behavior}を保持しています。この方式は実機未検証です。`;
                sequence.append(note);
            }
            const stepPicker = document.createElement('select');
            stepPicker.className = 'dads-select__select';
            stepPicker.dataset.size = 'md';
            stepPicker.setAttribute('aria-label', '照明の段階');
            const activeStep = Math.min(Number(sequenceSteps.get(event) ?? 0), event.sequence.length - 1);
            event.sequence.forEach((step, j) => stepPicker.add(new Option(`段階 ${j+1} / ${event.sequence.length}`, String(j))));
            stepPicker.value = String(activeStep);
            stepPicker.addEventListener('change', () => {
                sequenceSteps.set(event, Number(stepPicker.value));
                renderMacroRows();
            });
            sequence.append(stepPicker);
            event.sequence.forEach((step, j) => {
                if (j !== activeStep) return;
                const line = document.createElement('div');
                line.className = 'macro-row';
                const add = (label, control) => {
                    const wrap = document.createElement('label');
                    wrap.textContent = label;
                    control.setAttribute('aria-label', `${i+1}行目 照明${j+1} ${label}`);
                    wrap.append(control);
                    line.append(wrap);
                };
                const mode = document.createElement('select');
                mode.className = 'dads-select__select';
                mode.dataset.size = 'md';
                LIGHT_MODES.forEach(([value, label]) => mode.add(new Option(label, value)));
                mode.value = step.mode;
                mode.addEventListener('change', () => step.mode = mode.value);
                add('モード', mode);
                const color = document.createElement('select');
                color.className = 'dads-select__select';
                color.dataset.size = 'md';
                color.add(new Option('色循環', '0'));
                for (let c = 1; c <= 7; c++) color.add(new Option(`色${c}`, String(c)));
                color.value = String(step.color ?? 0);
                color.addEventListener('change', () => step.color = Number(color.value));
                add('色', color);
                const duration = document.createElement('input');
                duration.type = 'number';
                duration.min = '100';
                duration.max = '25500';
                duration.step = '100';
                duration.value = String(step.duration_ms ?? 1000);
                duration.addEventListener('input', () => step.duration_ms = Number(duration.value));
                add('持続時間（ms）', duration);
                for (const [label, delta] of [
                        ['前へ', -1],
                        ['後へ', 1],
                        ['削除', 0]
                    ]) {
                    const button = document.createElement('button');
                    button.className = 'dads-button';
                    button.dataset.size = 'sm';
                    button.dataset.type = 'text';
                    button.textContent = label;
                    button.setAttribute('aria-label', `${i+1}行目 照明${j+1}を${label}`);
                    button.disabled = delta ? j + delta < 0 || j + delta >= event.sequence.length : event.sequence.length === 1;
                    button.addEventListener('click', () => {
                        if (delta)[event.sequence[j], event.sequence[j + delta]] = [event.sequence[j + delta], event.sequence[j]];
                        else event.sequence.splice(j, 1);
                        renderMacroRows();
                    });
                    line.append(button);
                }
                sequence.append(line);
            });
            const add = document.createElement('button');
            add.className = 'dads-button';
            add.dataset.size = 'sm';
            add.dataset.type = 'outline';
            add.textContent = '照明の段階を追加';
            add.disabled = event.sequence.length >= 16;
            add.addEventListener('click', () => {
                event.sequence.push({
                    mode: 'constant',
                    color: 1,
                    duration_ms: 1000
                });
                renderMacroRows();
            });
            sequence.append(add);
            row.append(sequence);
        }
        const delay = document.createElement('input');
        delay.type = 'number';
        delay.min = '8';
        delay.max = '10000';
        delay.step = '8';
        delay.value = String(event.delay ?? 8);
        delay.addEventListener('input', () => event.delay = Number(delay.value));
        field('操作後の待機（ms）', delay);
        const actions = document.createElement('div');
        actions.className = 'macro-row-actions';
        for (const [label, delta] of [
                ['上へ', -1],
                ['下へ', 1],
                ['削除', 0]
            ]) {
            const button = document.createElement('button');
            button.className = 'dads-button';
            button.dataset.size = 'sm';
            button.dataset.type = 'text';
            button.textContent = label;
            button.setAttribute('aria-label', `${i+1}行目を${label}`);
            button.disabled = delta !== 0 && (i + delta < 0 || i + delta >= macroRows.length);
            button.addEventListener('click', () => {
                if (delta)[macroRows[i], macroRows[i + delta]] = [macroRows[i + delta], macroRows[i]];
                else macroRows.splice(i, 1);
                selectedRow = delta ? i + delta : i;
                renderMacroRows();
            });
            actions.append(button);
        }
        row.append(actions);
        container.append(row);
    });
    enhanceControls(container);
    if (hadFocus) {
        const target = [...container.querySelectorAll('[aria-label]')].find(el => el.getAttribute('aria-label') === focusLabel);
        (target ?? $('macro-row-select')).focus();
    }
    requestAnimationFrame(fitWorkspace);
}
$('macro-add').addEventListener('click', () => {
    if (macroRows.length >= 275) {
        message('275行まで追加できます。', 'error');
        return;
    }
    macroRows.push({
        type: 'delay',
        delay: 8
    });
    selectedRow = macroRows.length - 1;
    renderMacroRows();
});
$('stage-macro').addEventListener('click', () => {
    if (!validateFields($('macro-controls'))) return;
    const spec = {
        mode: $('macro-mode').value,
        repeat: Number($('macro-repeat').value),
        events: macroRows
    };
    try {
        compileMacro(spec);
        stage(spec);
    } catch (error) {
        fieldError($('macro-row-select'), error.message);
    }
});
$('read-macro').addEventListener('click', () => run(async () => {
    const target = selected;
    message('本体のマクロを読み取っています…');
    const full = await usbLock(() => session.exclusive(() => session.fullSnapshot()));
    if (!full.data.every((v, i) => v === snapshot.data[i])) throw new Error('本体の設定が変わっています。再読み取りしてからお試しください。');
    const spec = decodeMacro(full.image, full.base, offset(target));
    macroRows = spec.events;
    $('macro-mode').value = spec.mode;
    $('macro-repeat').value = String(spec.repeat);
    selectedRow = 0;
    editSequence();
    renderMacroRows();
    message('本体のマクロを編集画面へ読み込みました。変更を割り当てて保存するまで本体は変わりません。', 'success');
}));
renderMacroRows();
let recording = null;

function endRecording({
    showEditor = true
} = {}) {
    if (!recording) return;
    const active = recording;
    recording = null;
    $('record-start').disabled = false;
    $('record-stop').disabled = true;
    try {
        const rows = active.finish(performance.now());
        if (rows.length) {
            selectedRow = 0;
            macroRows = rows;
            renderMacroRows();
        }
        if (showEditor) editSequence();
        $('record-status').textContent = `${rows.length}件の操作を編集画面へ移しました。内容を確認してから割り当ててください。`;
    } catch (error) {
        message(error.message, 'error');
    }
}

function recordOperation(event) {
    if (!recording) return;
    try {
        recording.append(event, performance.now());
        $('record-status').textContent = `記録中：${recording.events.length}件。Escで終了できます。`;
    } catch (error) {
        endRecording();
        message(error.message, 'error');
    }
}
$('record-start').addEventListener('click', () => {
    if (busy) return;
    recording = new MacroRecorder();
    $('record-start').disabled = true;
    $('record-stop').disabled = false;
    $('record-status').textContent = '記録中です。この欄で操作し、Escで終了してください。';
    $('record-area').focus();
});
$('record-stop').addEventListener('click', endRecording);
$('record-area').addEventListener('blur', endRecording);
for (const type of ['keydown', 'keyup']) $('record-area').addEventListener(type, event => {
    if (!recording) return;
    event.preventDefault();
    if (event.code === 'Escape') {
        if (type === 'keydown') endRecording();
        return;
    }
    const key = recordedKey(event.code);
    if (key === undefined) {
        $('record-status').textContent = `このキーは自動記録に未対応です：${event.code}。編集画面で追加できます。`;
        return;
    }
    if (type === 'keydown' && (event.repeat || recording.held.has(`key:${key}`))) return;
    if (type === 'keyup' && !recording.held.has(`key:${key}`)) return;
    recordOperation({
        type: type === 'keydown' ? 'key-down' : 'key-up',
        key
    });
});
for (const type of ['mousedown', 'mouseup']) $('record-area').addEventListener(type, event => {
    if (!recording) return;
    event.preventDefault();
    const button = ['left', 'middle', 'right'][event.button];
    if (!button) return;
    if (type === 'mouseup' && !recording.held.has(`mouse:${button}`)) return;
    recordOperation({
        type: type === 'mousedown' ? 'mouse-down' : 'mouse-up',
        button
    });
});
$('record-area').addEventListener('wheel', event => {
    if (recording) {
        event.preventDefault();
        recordOperation({
            type: 'scroll',
            steps: event.deltaY < 0 ? 1 : -1
        });
    }
}, {
    passive: false
});
$('record-area').addEventListener('contextmenu', event => event.preventDefault());
enhanceControls();
showTask('light', 'basic');
showTask('macro', 'shortcut');
showLibraryView();
selectSettingsTab(location.hash.replace('#page-', ''));
try {
    const saved = localStorage.getItem(RECOVERY_KEY);
    if (saved) {
        const doc = JSON.parse(saved);
        await parseBackup(doc);
        recoveryDoc = doc;
    }
} catch {
    /* Corrupt local recovery never becomes a writable configuration. */
}
if (!('hid' in navigator) || !window.isSecureContext) {
    message('PC版Chrome・EdgeでHTTPSのページを開いてください。デモはこのまま利用できます。', 'warning', '実機接続に未対応の環境です');
}
render();