// background.js
console.log('🚀 Activity Monitor запущен');

let activeTabId = null;
let activeDomain = null;
let activeStart = Date.now();
let siteTimes = {};
let serverAvailable = false;
let currentUserId = null; // Будем хранить user_id из Flask

// Получаем домен
function getDomain(url) {
    try {
        return new URL(url).hostname.toLowerCase();
    } catch {
        return null;
    }
}

// Сохраняем время
function saveTime() {
    if (activeDomain && activeStart) {
        const now = Date.now();
        const seconds = Math.floor((now - activeStart) / 1000);

        if (seconds > 0) {
            siteTimes[activeDomain] = (siteTimes[activeDomain] || 0) + seconds;
        }

        activeStart = now;
    }
}

// Смена вкладки
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    saveTime();

    try {
        const tab = await chrome.tabs.get(activeInfo.tabId);
        activeTabId = activeInfo.tabId;
        activeDomain = getDomain(tab.url);
        activeStart = Date.now();
    } catch (error) {
        console.error('❌ Ошибка:', error);
    }
});

// Обновление URL
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (tabId === activeTabId && changeInfo.url) {
        saveTime();
        activeDomain = getDomain(changeInfo.url);
        activeStart = Date.now();
    }
});

// ========== ПРОВЕРКА USER_ID ==========
async function checkUserId() {
    try {
        const response = await fetch('http://127.0.0.1:5000/current_user', {
            method: 'GET',
            cache: 'no-cache',
            timeout: 2000
        });

        if (response.ok) {
            const data = await response.json();

            if (data.user_id) {
                currentUserId = data.user_id;
                console.log(`✅ Авторизован пользователь ID: ${currentUserId}`);
                return true;
            } else {
                currentUserId = null;
                console.log('⚠️ Пользователь не авторизован. Авторизуйтесь в Flet приложении.');
                return false;
            }
        }
    } catch (error) {
        console.log('❌ Не удалось проверить user_id:', error.message);
    }

    return false;
}

// ========== ПРОВЕРКА СЕРВЕРА ==========
async function checkServer() {
    try {
        const response = await fetch('http://127.0.0.1:5000/ping', {
            method: 'GET',
            cache: 'no-cache'
        });

        if (response.ok) {
            const data = await response.json();
            serverAvailable = true;

            // Проверяем user_id при проверке сервера
            if (data.user_id) {
                currentUserId = data.user_id;
            }

            return true;
        }
    } catch (error) {
        console.log('❌ Сервер недоступен');
        serverAvailable = false;
        currentUserId = null;
    }

    return false;
}

// ========== ОТПРАВКА ДАННЫХ ==========
async function sendData() {
    // 1. Проверяем есть ли данные
    if (Object.keys(siteTimes).length === 0) {
        return;
    }

    // 2. Проверяем доступность сервера
    if (!serverAvailable) {
        const isAvailable = await checkServer();
        if (!isAvailable) {
            console.log('⚠️ Сервер недоступен, сохраняю данные');
            return;
        }
    }

    // 3. Проверяем user_id ПЕРЕД отправкой!
    if (!currentUserId) {
        const hasUser = await checkUserId();
        if (!hasUser) {
            console.log('❌ ОТМЕНА ОТПРАВКИ: Пользователь не авторизован');
            console.log('👉 Авторизуйтесь в Flet приложении');

            // Очищаем данные, если пользователь не авторизован
            // (чтобы не копить данные для неавторизованного пользователя)
            siteTimes = {};
            return;
        }
    }

    console.log(`📤 Отправка данных для user ${currentUserId}:`, siteTimes);

    const dataToSend = { ...siteTimes };

    try {
        const response = await fetch('http://127.0.0.1:5000/log_activity', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                site_times: dataToSend,
                timestamp: Date.now()
            })
        });

        if (response.ok) {
            const result = await response.json();
            console.log(`✅ Данные для user ${currentUserId} отправлены:`, result);
            siteTimes = {}; // Очищаем только после успешной отправки
        } else if (response.status === 403) {
            // 403 - доступ запрещен (нет user_id)
            const error = await response.json();
            console.log(`❌ ОТКАЗ СЕРВЕРА: ${error.message}`);
            currentUserId = null; // Сбрасываем user_id
            siteTimes = {}; // Очищаем накопленные данные
        } else {
            console.log(`❌ Ошибка сервера: ${response.status}`);
            serverAvailable = false;
        }
    } catch (error) {
        console.error('❌ Ошибка отправки:', error.message);
        serverAvailable = false;
    }
}

// ========== ТАЙМЕРЫ ==========
// Сохраняем время каждые 5 секунд
setInterval(() => {
    saveTime();
}, 5000);

// Отправляем данные каждые 30 секунд
setInterval(() => {
    sendData();
}, 30000);

// Проверяем сервер и user_id при запуске
setTimeout(async () => {
    await checkServer();
    await checkUserId();
}, 2000);

// Проверяем user_id каждую минуту (на случай выхода/входа)
setInterval(async () => {
    await checkUserId();
}, 60000);

// Отладочная информация
setInterval(() => {
    console.log('📊 Статус:', {
        serverAvailable,
        currentUserId,
        activeDomain,
        siteTimesCount: Object.keys(siteTimes).length
    });
}, 60000); // Каждую минуту

// ========== ОТЛАДКА ==========
// Функции для консоли
window.debugMonitor = {
    getStatus: () => ({
        serverAvailable,
        currentUserId,
        activeDomain,
        siteTimes,
        activeStart,
        dataSize: Object.keys(siteTimes).length
    }),
    forceSend: () => sendData(),
    checkUser: () => checkUserId(),
    checkServer: () => checkServer(),
    clearData: () => {
        siteTimes = {};
        console.log('🧹 Данные очищены');
    }
};

console.log('✅ Мониторинг активности начат');
console.log('🔍 Проверяем авторизацию...');