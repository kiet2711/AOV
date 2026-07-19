document.addEventListener('DOMContentLoaded', function () {
    const tokenInput = document.getElementById('token');
    const imageInput = document.getElementById('imageInput');
    const imageElement = document.getElementById('image');
    const cropperWrapper = document.getElementById('cropperWrapper');
    const uploadBtn = document.getElementById('uploadBtn');
    const logBox = document.getElementById('logBox');
    const isShareInput = document.getElementById('isShare');
    
    let cropper = null;
    let logInterval = null;

    // Show cropper when image selected
    imageInput.addEventListener('change', function (e) {
        const files = e.target.files;
        if (files && files.length > 0) {
            const file = files[0];
            const reader = new FileReader();
            
            reader.onload = function (e) {
                imageElement.src = e.target.result;
                cropperWrapper.style.display = 'block';
                
                if (cropper) {
                    cropper.destroy();
                }
                
                cropper = new Cropper(imageElement, {
                    aspectRatio: 1080 / 1701,
                    viewMode: 1,
                    autoCropArea: 1,
                    responsive: true,
                });
                
                checkReady();
            };
            
            reader.readAsDataURL(file);
        }
    });

    tokenInput.addEventListener('input', checkReady);

    function checkReady() {
        if (tokenInput.value.trim() !== '' && cropper) {
            uploadBtn.disabled = false;
        } else {
            uploadBtn.disabled = true;
        }
    }

    uploadBtn.addEventListener('click', function () {
        if (!cropper) return;
        
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Đang xử lý...';
        logBox.innerHTML = '';
        
        // Start polling logs
        if (logInterval) clearInterval(logInterval);
        logInterval = setInterval(fetchLogs, 1000);

        // Get cropped image blob
        cropper.getCroppedCanvas({
            width: 1080,
            height: 1701,
            fillColor: '#000',
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high',
        }).toBlob(function (blob) {
            const formData = new FormData();
            formData.append('file', blob, 'cropped.jpg');
            formData.append('token', tokenInput.value.trim());
            formData.append('is_share', isShareInput.checked);
            formData.append('mode', document.getElementById('mode').value);

            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    appendLog("Lỗi: " + data.message, "text-red");
                    stopPolling();
                }
            })
            .catch(error => {
                appendLog("Lỗi kết nối server: " + error, "text-red");
                stopPolling();
            });
        }, 'image/jpeg', 0.9);
    });

    function fetchLogs() {
        fetch('/logs')
            .then(res => res.json())
            .then(data => {
                if (data.logs && data.logs.length > 0) {
                    data.logs.forEach(log => appendLog(log));
                    // Check if done
                    if (data.logs.some(l => l.includes("== HOAN THANH =="))) {
                        stopPolling();
                    }
                }
            })
            .catch(console.error);
    }

    function appendLog(msg, colorClass = "") {
        const div = document.createElement('div');
        div.textContent = msg;
        if (colorClass) div.className = colorClass;
        
        // Simple color parsing based on keywords
        if (msg.includes("OK") || msg.includes("Thanh cong")) div.className = "text-green";
        else if (msg.includes("FAIL") || msg.includes("THAT BAI") || msg.includes("Loi") || msg.includes("Exception")) div.className = "text-red";
        else if (msg.includes("START") || msg.includes("DONE")) div.className = "text-blue";

        logBox.appendChild(div);
        logBox.scrollTop = logBox.scrollHeight;
    }

    function stopPolling() {
        if (logInterval) {
            clearInterval(logInterval);
            logInterval = null;
        }
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Tải lên & Xử lý';
    }
});
