document.addEventListener('DOMContentLoaded', function () {
    initExerciseModal();
    initFilterButtons();
    initFlashClose();
});

function showFlash(msg, type) {
    type = type || 'info';
    var el = document.getElementById('flash-messages');
    if (!el) return;
    var div = document.createElement('div');
    div.className = 'flash flash-' + type;
    div.textContent = msg;
    el.appendChild(div);
    setTimeout(function () {
        div.style.opacity = '0';
        setTimeout(function () { div.remove(); }, 300);
    }, 4000);
}

function initFlashClose() {
    document.querySelectorAll('.flash').forEach(function (el) {
        setTimeout(function () {
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 300);
        }, 4000);
    });
}

function initFilterButtons() {
    var section = document.querySelector('.exercises-page');
    if (!section || section.dataset.filterBound) return;
    section.dataset.filterBound = '1';
    section.addEventListener('click', function (e) {
        var btn = e.target.closest('.filter-btn');
        if (!btn) return;
        section.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var cat = btn.getAttribute('data-category');
        section.querySelectorAll('.exercise-card').forEach(function (card) {
            if (cat === 'all' || card.getAttribute('data-category') === cat) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
    });
}

function initExerciseModal() {
    var modal = document.getElementById('exercise-modal');
    var closeBtn = modal ? modal.querySelector('.modal-close') : null;
    var submitBtn = document.getElementById('submit-exercise');
    var list = document.getElementById('games-list') || document.getElementById('exercises-list');
    if (!modal) return;
    if (closeBtn) closeBtn.addEventListener('click', function () { closeModal(); });
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });
    if (list && !list.dataset.exerciseBound) {
        list.dataset.exerciseBound = '1';
        list.addEventListener('click', function (e) {
            var btn = e.target.closest('.btn-exercise');
            if (!btn) return;
            var id = btn.getAttribute('data-id');
            var type = btn.getAttribute('data-type');
            var content = parseJsonAttr(btn.getAttribute('data-content'));
            var answer = parseJsonAttr(btn.getAttribute('data-answer'));
            var card = btn.closest('.exercise-card');
            var title = card ? card.querySelector('h3').textContent : '';
            openExercise(parseInt(id, 10), type, content, answer, title);
        });
    }
    if (submitBtn && !submitBtn.dataset.boundSubmit) {
        submitBtn.dataset.boundSubmit = '1';
        submitBtn.addEventListener('click', submitExercise);
    }
}

function parseJsonAttr(val) {
    if (val == null || val === '') return val;
    try {
        return JSON.parse(val);
    } catch (e) {
        return val;
    }
}

var currentExercise = {
    id: null,
    type: null,
    content: null,
    answer: null,
    startTime: null,
    attempts: 0,
    userAnswer: null
};

var submitExerciseInFlight = false;

function resetExerciseSubmitUi() {
    var btn = document.getElementById('submit-exercise');
    var fb = document.getElementById('modal-feedback');
    if (btn) {
        btn.disabled = false;
        btn.textContent = 'تحقق من الإجابة';
        btn.removeAttribute('data-action');
        btn.removeAttribute('data-result-ok');
    }
    if (fb) {
        fb.textContent = '';
        fb.className = 'modal-feedback hidden';
        fb.setAttribute('hidden', '');
        fb.setAttribute('aria-hidden', 'true');
    }
}

function setModalFeedback(kind, message) {
    var fb = document.getElementById('modal-feedback');
    if (!fb) return;
    fb.className = 'modal-feedback modal-feedback--' + kind;
    fb.textContent = message;
    fb.removeAttribute('hidden');
    fb.removeAttribute('aria-hidden');
    try {
        fb.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (e) {}
}

function openExercise(id, type, content, answer, title) {
    resetExerciseSubmitUi();
    currentExercise = {
        id: id,
        type: type,
        content: content,
        answer: answer,
        startTime: Date.now(),
        attempts: 0,
        userAnswer: null
    };
    var modal = document.getElementById('exercise-modal');
    var modalTitle = document.getElementById('modal-title');
    var modalBody = document.getElementById('modal-body');
    modalTitle.textContent = title;
    modalBody.innerHTML = '';
    var contentObj = (typeof content === 'string') ? (function () { try { return JSON.parse(content); } catch (e) { return [content]; } })() : (Array.isArray(content) ? content : [content]);
    var answerObj = (typeof answer === 'string') ? (function () { try { return JSON.parse(answer); } catch (e) { return answer; } })() : answer;
    if (type === 'order') {
        renderOrderExercise(modalBody, contentObj);
    } else if (type === 'choice') {
        var opts = Array.isArray(contentObj) ? contentObj : [contentObj];
        renderChoiceExercise(modalBody, opts, answerObj);
    } else if (type === 'true_false') {
        var opts = Array.isArray(contentObj) ? contentObj : ['صح', 'خطأ'];
        renderTrueFalseExercise(modalBody, opts, answerObj);
    } else {
        var opts = Array.isArray(contentObj) ? contentObj : [contentObj];
        renderChoiceExercise(modalBody, opts, answerObj);
    }
    modal.classList.remove('hidden');
}

function renderOrderExercise(container, items) {
    var hint = document.createElement('p');
    hint.className = 'sort-hint';
    hint.textContent = 'اسحب العناصر وأفلتها بالترتيب الصحيح (سحب وإفلات).';
    container.appendChild(hint);
    var list = document.createElement('div');
    list.className = 'sort-container';
    list.setAttribute('data-sortable', 'true');
    var shuffled = items.slice().sort(function () { return Math.random() - 0.5; });
    shuffled.forEach(function (item) {
        var el = document.createElement('div');
        el.className = 'sort-item';
        el.textContent = item;
        el.setAttribute('data-value', item);
        list.appendChild(el);
    });
    makeSortable(list);
    container.appendChild(list);
}

function makeSortable(container) {
    var items = container.querySelectorAll('.sort-item');
    var dragged = null;
    items.forEach(function (item) {
        item.setAttribute('draggable', 'true');
        item.addEventListener('dragstart', function (e) {
            dragged = item;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', item.textContent);
        });
        item.addEventListener('dragover', function (e) {
            e.preventDefault();
            if (dragged !== item) {
                var rect = item.getBoundingClientRect();
                var mid = rect.top + rect.height / 2;
                if (e.clientY < mid) {
                    container.insertBefore(dragged, item);
                } else {
                    container.insertBefore(dragged, item.nextSibling);
                }
            }
        });
        item.addEventListener('dragend', function () {
            dragged = null;
        });
    });
}

function renderChoiceExercise(container, options, correctAnswer) {
    var wrap = document.createElement('div');
    wrap.className = 'choices-container';
    options.forEach(function (opt) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'choice-btn';
        btn.textContent = opt;
        btn.setAttribute('data-value', opt);
        btn.addEventListener('click', function () {
            wrap.querySelectorAll('.choice-btn').forEach(function (b) { b.classList.remove('selected'); });
            btn.classList.add('selected');
            currentExercise.userAnswer = opt;
        });
        wrap.appendChild(btn);
    });
    container.appendChild(wrap);
}

function renderTrueFalseExercise(container, options, correctAnswer) {
    var wrap = document.createElement('div');
    wrap.className = 'true-false-container';
    options.forEach(function (opt) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'true-false-btn';
        btn.textContent = opt;
        btn.setAttribute('data-value', opt);
        btn.addEventListener('click', function () {
            wrap.querySelectorAll('.true-false-btn').forEach(function (b) { b.classList.remove('selected'); });
            btn.classList.add('selected');
            currentExercise.userAnswer = opt;
        });
        wrap.appendChild(btn);
    });
    container.appendChild(wrap);
}

function getOrderUserAnswer() {
    var container = document.querySelector('.sort-container');
    if (!container) return null;
    var items = container.querySelectorAll('.sort-item');
    return Array.from(items).map(function (i) { return i.getAttribute('data-value'); });
}

function checkOrderAnswer(userOrder, correctAnswer) {
    var correct = Array.isArray(correctAnswer) ? correctAnswer : (typeof correctAnswer === 'string' ? (function () { try { var r = JSON.parse(correctAnswer); return Array.isArray(r) ? r : [r]; } catch (e) { return [correctAnswer]; } })() : [correctAnswer]);
    if (userOrder.length !== correct.length) return { ok: false, type: 'ترتيب' };
    for (var i = 0; i < correct.length; i++) {
        if (userOrder[i] !== correct[i]) return { ok: false, type: 'ترتيب' };
    }
    return { ok: true };
}

function submitExercise() {
    var btn = document.getElementById('submit-exercise');
    if (btn && btn.getAttribute('data-action') === 'close') {
        closeModal();
        return;
    }

    if (submitExerciseInFlight) return;

    var isCorrect = false;
    var errorType = '';
    if (currentExercise.type === 'order') {
        var order = getOrderUserAnswer();
        if (!order || order.length === 0) {
            setModalFeedback('warn', 'يرجى ترتيب العناصر بالسحب والإفلات ثم الضغط على التحقق.');
            return;
        }
        var result = checkOrderAnswer(order, currentExercise.answer);
        isCorrect = result.ok;
        if (!isCorrect) errorType = result.type || 'ترتيب';
    } else {
        if (!currentExercise.userAnswer) {
            setModalFeedback('warn', 'يرجى اختيار إجابة قبل التحقق.');
            return;
        }
        var ans = currentExercise.answer;
        if (Array.isArray(ans)) {
            isCorrect = ans.indexOf(currentExercise.userAnswer) >= 0;
        } else {
            isCorrect = String(ans).trim() === String(currentExercise.userAnswer).trim();
        }
        if (!isCorrect) errorType = 'اختيار';
    }

    currentExercise.attempts += 1;
    var timeSpent = (Date.now() - currentExercise.startTime) / 1000;

    if (btn) {
        submitExerciseInFlight = true;
        btn.disabled = true;
        btn.textContent = 'جاري حفظ النتيجة…';
        btn.removeAttribute('data-action');
        btn.removeAttribute('data-result-ok');
    }

    var feedbackEl = document.getElementById('modal-feedback');
    if (feedbackEl) {
        feedbackEl.className = 'modal-feedback hidden';
        feedbackEl.textContent = '';
    }

    sendAttempt(currentExercise.id, isCorrect, timeSpent, currentExercise.attempts, errorType, function () {
        submitExerciseInFlight = false;
        if (!btn) return;

        if (isCorrect) {
            setModalFeedback('ok', 'أحسنت! إجابة صحيحة — يمكنك إغلاق النافذة ومتابعة المراحل.');
            btn.textContent = 'إغلاق';
            btn.setAttribute('data-action', 'close');
            btn.setAttribute('data-result-ok', '1');
            btn.disabled = false;
        } else {
            setModalFeedback('err', 'ليس بعد — راجع السؤال وحاول مجدداً.');
            btn.textContent = 'تحقق من الإجابة';
            btn.disabled = false;
        }
    });
}

function sendAttempt(exerciseId, isCorrect, timeSpent, attemptsCount, errorType, callback) {
    var xhr = new XMLHttpRequest();
    var base = typeof API !== 'undefined' ? API : '';
    xhr.open('POST', base + '/api/submit_attempt');
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.withCredentials = true;
    xhr.timeout = 25000;
    xhr.onerror = xhr.ontimeout = function () {
        if (callback) callback();
    };
    xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        if (xhr.status === 200) {
            try {
                var data = JSON.parse(xhr.responseText);
                if (data.success && data.level) {
                    var levelEl = document.querySelector('.stat-value');
                    if (levelEl) levelEl.textContent = data.level;
                }
            } catch (e) {}
        } else if (xhr.status === 403 || xhr.status === 400) {
            try {
                var err = JSON.parse(xhr.responseText);
                if (err && err.error) {
                    setModalFeedback('err', err.error);
                }
            } catch (e) {}
        }
        if (callback) callback();
    };
    xhr.send(JSON.stringify({
        exercise_id: exerciseId,
        is_correct: isCorrect,
        time_spent: timeSpent,
        attempts_count: attemptsCount,
        error_type: errorType || null
    }));
}

function closeModal() {
    var modal = document.getElementById('exercise-modal');
    var btn = document.getElementById('submit-exercise');
    var flashSuccess = btn && btn.getAttribute('data-result-ok') === '1';
    if (modal) modal.classList.add('hidden');
    resetExerciseSubmitUi();
    if (flashSuccess) {
        showFlash('أحسنت! إجابة صحيحة — واصل المرحلة التالية', 'success');
    }
}
