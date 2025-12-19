// content.js
(function() {
    'use strict';

    let lastActivityTime = Date.now();
    let isUserActive = true;
    let activityCheckInterval = null;
    let videoPlaying = false;
    let audioPlaying = false;

    // События активности пользователя
    const activityEvents = [
        'mousedown', 'mousemove', 'click', 'scroll', 'keydown',
        'touchstart', 'touchend', 'touchmove', 'wheel',
        'input', 'change', 'focus', 'blur'
    ];

    // Функция обработки активности
    function handleUserActivity() {
        lastActivityTime = Date.now();

        if (!isUserActive) {
            isUserActive = true;
            // Сообщаем background script об активности
            chrome.runtime.sendMessage({ type: 'USER_ACTIVE' });
        }
    }

    // Отслеживание медиа элементов
    function trackMediaElements() {
        // Отслеживаем видео
        document.querySelectorAll('video').forEach(video => {
            video.addEventListener('play', () => {
                videoPlaying = true;
                chrome.runtime.sendMessage({ type: 'MEDIA_PLAYING' });
            });
            video.addEventListener('pause', () => {
                videoPlaying = false;
                checkIfInactive();
            });
            video.addEventListener('ended', () => {
                videoPlaying = false;
                checkIfInactive();
            });
        });

        // Отслеживаем аудио
        document.querySelectorAll('audio').forEach(audio => {
            audio.addEventListener('play', () => {
                audioPlaying = true;
                chrome.runtime.sendMessage({ type: 'MEDIA_PLAYING' });
            });
            audio.addEventListener('pause', () => {
                audioPlaying = false;
                checkIfInactive();
            });
            audio.addEventListener('ended', () => {
                audioPlaying = false;
                checkIfInactive();
            });
        });

        // Отслеживаем создание новых медиа элементов (для динамических страниц)
        const observer = new MutationObserver(() => {
            trackMediaElements();
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    // Проверка на неактивность
    function checkIfInactive() {
        const inactiveTime = Date.now() - lastActivityTime;

        // Если неактивность более 30 секунд и нет играющего медиа
        if (inactiveTime > 30000 && !videoPlaying && !audioPlaying) {
            if (isUserActive) {
                isUserActive = false;
                chrome.runtime.sendMessage({ type: 'USER_INACTIVE' });
            }
        }
    }

    // Инициализация
    function initActivityTracker() {
        // Подписываемся на события активности
        activityEvents.forEach(event => {
            document.addEventListener(event, handleUserActivity, { passive: true });
        });

        // Начинаем отслеживать медиа элементы
        trackMediaElements();

        // Проверяем активность каждые 10 секунд
        activityCheckInterval = setInterval(checkIfInactive, 10000);

        // Проверяем текущие медиа элементы
        const videos = document.querySelectorAll('video');
        const audios = document.querySelectorAll('audio');

        videoPlaying = Array.from(videos).some(v => !v.paused);
        audioPlaying = Array.from(audios).some(a => !a.paused);

        if (videoPlaying || audioPlaying) {
            chrome.runtime.sendMessage({ type: 'MEDIA_PLAYING' });
        }

        // Обработка видимости страницы
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                chrome.runtime.sendMessage({ type: 'USER_INACTIVE' });
            } else {
                handleUserActivity();
            }
        });

        console.log('👀 Activity tracker initialized');
    }

    // Запускаем после полной загрузки страницы
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initActivityTracker);
    } else {
        initActivityTracker();
    }

    // Очистка при выгрузке страницы
    window.addEventListener('unload', () => {
        if (activityCheckInterval) {
            clearInterval(activityCheckInterval);
        }

        activityEvents.forEach(event => {
            document.removeEventListener(event, handleUserActivity);
        });
    });

})();