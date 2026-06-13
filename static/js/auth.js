/**
 * Authentication helpers for register.html and login.html
 * - Client-side validation
 * - Cloudflare Turnstile integration
 * - Form submission with CSRF protection
 */

(function () {
    'use strict';

    // --- Turnstile Callbacks ---
    let turnstileVerified = false;

    window.onTurnstileSuccess = function (token) {
        turnstileVerified = true;
        const err = document.getElementById('turnstile-error');
        if (err) err.classList.remove('visible');
        updateSubmitButton();
    };

    window.onTurnstileExpired = function () {
        turnstileVerified = false;
        updateSubmitButton();
    };

    window.onTurnstileError = function () {
        turnstileVerified = false;
        const err = document.getElementById('turnstile-error');
        if (err) {
            err.textContent = '人机验证失败，请刷新页面重试。';
            err.classList.add('visible');
        }
    };

    function updateSubmitButton() {
        const submitBtn = document.getElementById('submit-btn');
        if (!submitBtn) return;

        // For register page, also check invite code
        const inviteCode = document.getElementById('invite-code');
        const inviteOk = !inviteCode || inviteCode.value.trim().length > 0;

        submitBtn.disabled = !turnstileVerified || !inviteOk;
    }

    // --- Password Strength Meter ---
    function updatePasswordStrength(password, barId, textId) {
        const bar = document.getElementById(barId);
        const text = document.getElementById(textId);
        if (!bar || !text) return;

        let score = 0;
        if (password.length >= 8) score++;
        if (/[A-Z]/.test(password)) score++;
        if (/[a-z]/.test(password)) score++;
        if (/[0-9]/.test(password)) score++;
        if (/[^A-Za-z0-9]/.test(password)) score++;

        bar.className = 'strength-bar';
        if (score <= 1 && password.length > 0) {
            bar.classList.add('weak');
            text.textContent = '密码强度：弱';
        } else if (score === 2) {
            bar.classList.add('fair');
            text.textContent = '密码强度：一般';
        } else if (score === 3) {
            bar.classList.add('good');
            text.textContent = '密码强度：良好';
        } else if (score >= 4) {
            bar.classList.add('strong');
            text.textContent = '密码强度：强';
        } else {
            text.textContent = '密码强度';
        }
    }

    // --- Toggle Password Visibility ---
    document.querySelectorAll('.toggle-password').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const input = this.parentElement.querySelector('input');
            if (input.type === 'password') {
                input.type = 'text';
                this.textContent = '🙈';
            } else {
                input.type = 'password';
                this.textContent = '👁️';
            }
        });
    });

    // --- Clear error on input ---
    function clearError(inputId) {
        const err = document.getElementById(inputId + '-error');
        if (err) err.classList.remove('visible');
    }

    document.querySelectorAll('.auth-form input').forEach(function (input) {
        input.addEventListener('input', function () {
            clearError(this.id);
            if (this.id === 'invite-code') {
                updateSubmitButton();
            }
        });
    });

    // --- Password strength for register ---
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('input', function () {
            updatePasswordStrength(this.value, 'strength-bar', 'strength-text');
            // Check confirm match
            const confirm = document.getElementById('password-confirm');
            const confirmErr = document.getElementById('password-confirm-error');
            if (confirm && confirm.value && this.value !== confirm.value) {
                confirmErr.textContent = '两次输入的密码不一致';
                confirmErr.classList.add('visible');
            } else if (confirm && confirm.value) {
                confirmErr.classList.remove('visible');
            }
        });
    }

    const confirmInput = document.getElementById('password-confirm');
    if (confirmInput) {
        confirmInput.addEventListener('input', function () {
            const password = document.getElementById('password');
            const err = document.getElementById('password-confirm-error');
            if (password && this.value !== password.value) {
                err.textContent = '两次输入的密码不一致';
                err.classList.add('visible');
            } else {
                err.classList.remove('visible');
            }
        });
    }

    // --- Form Submission ---
    function showError(inputId, message) {
        const err = document.getElementById(inputId + '-error');
        if (err) {
            err.textContent = message;
            err.classList.add('visible');
        }
    }

    function validateRegisterForm() {
        let valid = true;
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const confirm = document.getElementById('password-confirm').value;
        const inviteCode = document.getElementById('invite-code').value.trim();

        if (!username) {
            showError('username', '请输入用户名');
            valid = false;
        } else if (!/^[a-zA-Z0-9_]{3,30}$/.test(username)) {
            showError('username', '用户名必须是3-30位字母、数字或下划线');
            valid = false;
        }

        if (!password) {
            showError('password', '请输入密码');
            valid = false;
        } else if (password.length < 8) {
            showError('password', '密码至少8位');
            valid = false;
        }

        if (password !== confirm) {
            showError('password-confirm', '两次输入的密码不一致');
            valid = false;
        }

        if (!inviteCode) {
            showError('invite-code', '请输入邀请码');
            valid = false;
        }

        if (!turnstileVerified) {
            showError('turnstile', '请完成人机验证');
            valid = false;
        }

        return valid;
    }

    function validateLoginForm() {
        let valid = true;
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        if (!username) {
            showError('username', '请输入用户名');
            valid = false;
        }
        if (!password) {
            showError('password', '请输入密码');
            valid = false;
        }
        if (!turnstileVerified) {
            showError('turnstile', '请完成人机验证');
            valid = false;
        }

        return valid;
    }

    function getFormData(form) {
        const fd = new FormData(form);
        const data = {};
        fd.forEach(function (value, key) {
            data[key] = value;
        });
        return data;
    }

    function disableForm(disable) {
        const submitBtn = document.getElementById('submit-btn');
        const inputs = document.querySelectorAll('.auth-form input');
        if (submitBtn) {
            submitBtn.disabled = disable;
            submitBtn.textContent = disable ? '处理中...' : (submitBtn.getAttribute('data-original') || submitBtn.textContent);
        }
        inputs.forEach(function (input) {
            input.disabled = disable;
        });
    }

    // Save original button text
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.setAttribute('data-original', submitBtn.textContent);
    }

    var form = document.getElementById('register-form') || document.getElementById('login-form');
    if (form) {
        var isRegister = !!document.getElementById('register-form');

        form.addEventListener('submit', async function (e) {
            e.preventDefault();

            if (isRegister) {
                if (!validateRegisterForm()) return;
            } else {
                if (!validateLoginForm()) return;
            }

            disableForm(true);

            var data = getFormData(this);
            data.remember_me = document.querySelector('input[name="remember_me"]')?.checked ? '1' : '0';

            try {
                var url = isRegister ? '/auth/register' : '/auth/login';
                var resp = await apiFetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                var result;
                try {
                    result = await resp.json();
                } catch (jsonErr) {
                    // Server returned non-JSON (usually a 500 error page)
                    console.error('Server returned non-JSON response (HTTP ' + resp.status + ')');
                    throw new Error('服务器错误 (HTTP ' + resp.status + ')，请检查服务器日志。');
                }

                if (!resp.ok) {
                    // Display the error
                    if (result.error) {
                        var flashArea = document.querySelector('.flash-messages');
                        if (!flashArea) {
                            flashArea = document.createElement('div');
                            flashArea.className = 'flash-messages';
                            form.parentElement.insertBefore(flashArea, form);
                        }
                        // Safely display errors using DOM manipulation
                        flashArea.textContent = '';
                        var flashDiv = document.createElement('div');
                        flashDiv.className = 'flash flash-error';
                        result.error.split('；').forEach(function (msg) {
                            if (msg.trim()) {
                                var line = document.createTextNode(msg.trim());
                                flashDiv.appendChild(line);
                                flashDiv.appendChild(document.createElement('br'));
                            }
                        });
                        flashArea.appendChild(flashDiv);
                    }
                    // Reset Turnstile
                    turnstileVerified = false;
                    if (window.turnstile) {
                        window.turnstile.reset();
                    }
                    updateSubmitButton();
                } else if (result.redirect) {
                    window.location.href = result.redirect;
                }
            } catch (err) {
                console.error('Auth request failed:', err);
                var msg;
                if (err && err.name === 'AbortError') {
                    msg = '请求超时 — 服务器无响应，请检查服务器是否正常运行 (http://' +
                          window.location.hostname + ':9888)。';
                } else if (err && err.message) {
                    msg = err.message;
                } else {
                    msg = '网络错误，请稍后重试。';
                }
                alert(msg);
            } finally {
                disableForm(false);
            }
        });
    }
})();
