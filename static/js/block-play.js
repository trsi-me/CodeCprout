(function () {
    var LEVELS = [
        {
            instruction: 'حرّك الأرنب ثلاث خطوات للأمام ثم اقفز للوصول إلى الهدف.',
            hint: 'اسحب أوامر «تحرك للأمام» ثلاث مرات ثم «اقفز».',
            execHint: '3 خطوات للأمام ثم قفز',
            target: ['forward', 'forward', 'forward', 'jump'],
            tiles: 5
        },
        {
            instruction: 'انعطف يميناً، ثم خطوتان للأمام، ثم اقفز.',
            hint: 'استخدم: انعطف يميناً — تحرك للأمام — تحرك للأمام — اقفز.',
            execHint: 'يمين ثم تقدّم ثم قفز',
            target: ['right', 'forward', 'forward', 'jump'],
            tiles: 5
        },
        {
            instruction: 'تراجع خطوة، ثم تقدّم مرتين، ثم انعطف يساراً.',
            hint: 'ترتيب: للخلف — للأمام — للأمام — يسار.',
            execHint: 'خلف، أمام، أمام، يسار',
            target: ['back', 'forward', 'forward', 'left'],
            tiles: 5
        }
    ];

    var CMD_LABELS = {
        forward: 'تحرك للأمام',
        back: 'تحرك للخلف',
        right: 'انعطف يميناً',
        left: 'انعطف يساراً',
        jump: 'اقفز'
    };

    var CMD_ICONS = {
        forward: 'fa-arrow-up',
        back: 'fa-arrow-down',
        right: 'fa-arrow-right',
        left: 'fa-arrow-left',
        jump: 'fa-up-long'
    };

    var state = {
        levelIndex: 0,
        sequence: [],
        attempts: 0,
        maxAttempts: 5,
        running: false
    };

    var els = {};

    function $(id) {
        return document.getElementById(id);
    }

    function currentLevel() {
        return LEVELS[state.levelIndex] || LEVELS[0];
    }

    function initEls() {
        els.workspace = $('workspace');
        els.toolbox = $('toolbox');
        els.instruction = $('play-instruction');
        els.execHint = $('exec-hint');
        els.attemptCount = $('attempt-count');
        els.feedback = $('play-feedback');
        els.actor = $('exec-actor');
        els.path = $('exec-path');
        els.progressDots = $('lesson-dots');
        els.motiv = $('motiv-text');
        els.points = $('header-points');
        els.badges = $('badge-count');
    }

    function getPoints() {
        var v = localStorage.getItem('cs_points');
        return v ? parseInt(v, 10) : 0;
    }

    function addPoints(n) {
        var t = getPoints() + n;
        localStorage.setItem('cs_points', String(t));
        if (els.points) els.points.textContent = t;
    }

    function renderToolbox() {
        if (!els.toolbox) return;
        els.toolbox.innerHTML = '';
        ['forward', 'back', 'right', 'left', 'jump'].forEach(function (cmd) {
            var b = createBlockEl(cmd, true);
            els.toolbox.appendChild(b);
        });
    }

    function createBlockEl(cmd, fromToolbox) {
        var span = document.createElement('span');
        span.className = 'code-block code-block--' + cmd;
        span.setAttribute('data-cmd', cmd);
        span.setAttribute('draggable', 'true');
        var ic = CMD_ICONS[cmd] || 'fa-square';
        span.innerHTML = '<i class="fa-solid ' + ic + '"></i> ' + CMD_LABELS[cmd];
        span.addEventListener('dragstart', onDragStart);
        span.addEventListener('dragend', onDragEnd);
        if (!fromToolbox) {
            span.addEventListener('dblclick', function () {
                span.remove();
                syncSequenceFromDom();
            });
        }
        return span;
    }

    var dragSrc = null;

    function onDragStart(e) {
        dragSrc = this;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', this.getAttribute('data-cmd'));
        this.classList.add('dragging');
    }

    function onDragEnd() {
        this.classList.remove('dragging');
        dragSrc = null;
        if (els.workspace) els.workspace.classList.remove('is-over');
    }

    function onWorkspaceDragOver(e) {
        e.preventDefault();
        els.workspace.classList.add('is-over');
    }

    function onWorkspaceDragLeave() {
        els.workspace.classList.remove('is-over');
    }

    function onWorkspaceDrop(e) {
        e.preventDefault();
        els.workspace.classList.remove('is-over');
        var cmd = e.dataTransfer.getData('text/plain');
        if (!cmd) return;
        var hint = els.workspace.querySelector('.workspace-hint');
        if (hint) hint.remove();
        if (dragSrc && dragSrc.parentNode === els.toolbox) {
            var block = createBlockEl(cmd, false);
            var after = getInsertBefore(els.workspace, e.clientX);
            if (after) els.workspace.insertBefore(block, after);
            else els.workspace.appendChild(block);
        } else if (dragSrc && dragSrc.parentNode === els.workspace) {
            var after2 = getInsertBefore(els.workspace, e.clientX);
            if (after2 && after2 !== dragSrc) els.workspace.insertBefore(dragSrc, after2);
            else if (!after2) els.workspace.appendChild(dragSrc);
        }
        syncSequenceFromDom();
    }

    function getInsertBefore(container, x) {
        var list = [].slice.call(container.querySelectorAll('.code-block:not(.dragging)'));
        list.sort(function (a, b) {
            var ra = a.getBoundingClientRect();
            var rb = b.getBoundingClientRect();
            var rowTol = 10;
            if (Math.abs(ra.top - rb.top) > rowTol) return ra.top - rb.top;
            return ra.left - rb.left;
        });
        for (var i = 0; i < list.length; i++) {
            var box = list[i].getBoundingClientRect();
            if (x < box.left + box.width / 2) return list[i];
        }
        return null;
    }

    function syncSequenceFromDom() {
        var blocks = [].slice.call(els.workspace.querySelectorAll('.code-block'));
        blocks.sort(function (a, b) {
            var ra = a.getBoundingClientRect();
            var rb = b.getBoundingClientRect();
            var rowTol = 10;
            if (Math.abs(ra.top - rb.top) > rowTol) return ra.top - rb.top;
            return ra.left - rb.left;
        });
        state.sequence = blocks.map(function (n) {
            return n.getAttribute('data-cmd');
        });
    }

    function renderLevel() {
        var L = currentLevel();
        if (els.instruction) els.instruction.textContent = L.instruction;
        if (els.execHint) els.execHint.textContent = L.execHint;
        if (els.attemptCount) els.attemptCount.textContent = state.attempts + '/' + state.maxAttempts;
        if (els.feedback) {
            els.feedback.className = 'feedback-banner';
            els.feedback.style.display = 'none';
            els.feedback.textContent = '';
        }
        clearWorkspace();
        buildPath(L.tiles || 5);
        placeActor(0);
        if (els.progressDots) {
            els.progressDots.innerHTML = '';
            LEVELS.forEach(function (_, i) {
                var d = document.createElement('span');
                if (i < state.levelIndex) d.classList.add('done');
                if (i === state.levelIndex) d.style.boxShadow = '0 0 0 2px #2C82C9';
                els.progressDots.appendChild(d);
            });
        }
        if (els.motiv) {
            els.motiv.innerHTML = '<span class="fw-normal">' + (L.hint || '') + '</span>';
        }
    }

    function clearWorkspace() {
        if (!els.workspace) return;
        els.workspace.innerHTML = '<span class="workspace-hint">اسحب الكتل هنا لبناء البرنامج (نقرتان على كتلة لحذفها)</span>';
        state.sequence = [];
    }

    function buildPath(n) {
        if (!els.path) return;
        els.path.innerHTML = '';
        for (var i = 0; i < n; i++) {
            var t = document.createElement('div');
            t.className = 'exec-tile' + (i === n - 1 ? ' exec-tile--goal' : '');
            if (i === n - 1) t.innerHTML = '<span class="goal-icon"><i class="fa-solid fa-flag-checkered"></i></span>';
            els.path.appendChild(t);
        }
    }

    function placeActor(tileIndex) {
        if (!els.actor || !els.path) return;
        var tiles = els.path.querySelectorAll('.exec-tile');
        if (!tiles.length) return;
        var n = tiles.length;
        var i = Math.min(Math.max(0, tileIndex), n - 1);
        var pct = n <= 1 ? 50 : (i / (n - 1)) * 100;
        els.actor.style.left = pct + '%';
        els.actor.style.right = 'auto';
        els.actor.style.transform = 'translateX(-50%)';
    }

    function runCode() {
        if (state.running) return;
        syncSequenceFromDom();
        var L = currentLevel();
        var ok = state.sequence.length === L.target.length;
        if (ok) {
            for (var i = 0; i < L.target.length; i++) {
                if (state.sequence[i] !== L.target[i]) {
                    ok = false;
                    break;
                }
            }
        } else {
            ok = false;
        }

        state.attempts++;
        if (els.attemptCount) els.attemptCount.textContent = Math.min(state.attempts, state.maxAttempts) + '/' + state.maxAttempts;

        if (ok) {
            state.running = true;
            animateSuccess(L, function () {
                state.running = false;
                if (els.feedback) {
                    els.feedback.className = 'feedback-banner ok';
                    els.feedback.style.display = 'block';
                    els.feedback.textContent = 'أحسنت! تسلسل الأوامر صحيح.';
                }
                addPoints(50);
                if (els.badges) els.badges.textContent = String(Math.min(99, state.levelIndex + 1 + Math.floor(getPoints() / 100)));
            });
        } else {
            if (els.feedback) {
                els.feedback.className = 'feedback-banner err';
                els.feedback.style.display = 'block';
                els.feedback.textContent = 'التسلسل غير مطابق للمهمة. راجع التعليمات وحاول مجدداً.';
            }
            if (state.attempts >= state.maxAttempts) {
                if (els.feedback) {
                    els.feedback.textContent = 'استنفدت المحاولات لهذه الجولة. اضغط إعادة تعيين.';
                }
            }
        }
    }

    function animateSuccess(L, done) {
        var step = 0;
        var maxStep = L.tiles;
        var id = setInterval(function () {
            step++;
            placeActor(Math.min(step, maxStep - 1));
            if (step >= maxStep) {
                clearInterval(id);
                if (typeof done === 'function') done();
            }
        }, 320);
    }

    function resetBoard() {
        state.attempts = 0;
        renderLevel();
    }

    function nextLevel() {
        if (state.levelIndex < LEVELS.length - 1) {
            state.levelIndex++;
            state.attempts = 0;
            renderLevel();
        } else {
            if (els.feedback) {
                els.feedback.className = 'feedback-banner ok';
                els.feedback.style.display = 'block';
                els.feedback.textContent = 'أكملت جميع الأنشطة في هذه الصفحة. انتقل إلى مكتبة الألعاب لمزيد من المراحل.';
            }
        }
    }

    function bindWorkspace() {
        if (!els.workspace) return;
        els.workspace.addEventListener('dragover', onWorkspaceDragOver);
        els.workspace.addEventListener('dragleave', onWorkspaceDragLeave);
        els.workspace.addEventListener('drop', onWorkspaceDrop);
    }

    function init() {
        initEls();
        renderToolbox();
        bindWorkspace();
        if (els.points) els.points.textContent = getPoints();
        if (els.badges) els.badges.textContent = '0';
        renderLevel();
        $('btn-run') && $('btn-run').addEventListener('click', runCode);
        $('btn-reset') && $('btn-reset').addEventListener('click', resetBoard);
        $('btn-next') && $('btn-next').addEventListener('click', nextLevel);
        $('btn-hint') && $('btn-hint').addEventListener('click', showHint);
    }

    function showHint() {
        var L = currentLevel();
        var text = L.hint || 'راجع التعليمات في الأعلى ورتّب الكتل على لوحة البرمجة.';
        if (els.feedback) {
            els.feedback.className = 'feedback-banner hint';
            els.feedback.style.display = 'block';
            els.feedback.textContent = text;
        }
        if (els.motiv) {
            els.motiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
