document.addEventListener('DOMContentLoaded', () => {
    // Tabs
    const tabUpload = document.getElementById('tabUpload');
    const tabLocal = document.getElementById('tabLocal');
    const uploadContainer = document.getElementById('uploadContainer');
    const localContainer = document.getElementById('localContainer');

    // Upload Elements
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const fileBanner = document.getElementById('fileBanner');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const convertBtn = document.getElementById('convertBtn');
    const removeFileBtn = document.getElementById('removeFileBtn');

    // Local Path Elements
    const localFileFormat = document.getElementById('localFileFormat');
    const localFilePath = document.getElementById('localFilePath');
    const convertLocalBtn = document.getElementById('convertLocalBtn');

    // Status / Output Elements
    const progressSection = document.getElementById('progressSection');
    const statusMessage = document.getElementById('statusMessage');
    const progressPercent = document.getElementById('progressPercent');
    const progressBar = document.getElementById('progressBar');
    const cancelBtn = document.getElementById('cancelBtn');
    
    const resultSection = document.getElementById('resultSection');
    const resultText = document.getElementById('resultText');
    const downloadBtn = document.getElementById('downloadBtn');
    
    const errorSection = document.getElementById('errorSection');
    const errorMessage = document.getElementById('errorMessage');

    let selectedFile = null;
    let pollInterval = null;
    let currentTaskId = null;

    // Tab Switchers
    tabUpload.addEventListener('click', () => {
        tabUpload.className = 'py-2.5 px-5 border-b-2 border-blue-600 text-blue-600 focus:outline-none flex items-center space-x-2';
        tabLocal.className = 'py-2.5 px-5 text-slate-500 hover:text-slate-700 focus:outline-none flex items-center space-x-2';
        uploadContainer.classList.remove('hidden');
        localContainer.classList.add('hidden');
        resetOutputState();
    });

    tabLocal.addEventListener('click', () => {
        tabLocal.className = 'py-2.5 px-5 border-b-2 border-amber-600 text-amber-600 focus:outline-none flex items-center space-x-2';
        tabUpload.className = 'py-2.5 px-5 text-slate-500 hover:text-slate-700 focus:outline-none flex items-center space-x-2';
        localContainer.classList.remove('hidden');
        uploadContainer.classList.add('hidden');
        resetOutputState();
    });

    function formatBytes(bytes, decimals = 2) {
        if (!bytes || bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    function resetOutputState() {
        progressSection.classList.add('hidden');
        resultSection.classList.add('hidden');
        errorSection.classList.add('hidden');
        if (pollInterval) clearInterval(pollInterval);
        currentTaskId = null;
    }

    function clearSelectedFile() {
        selectedFile = null;
        fileInput.value = '';
        fileBanner.classList.add('hidden');
        resetOutputState();
    }

    // Remove File Button Listener
    removeFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearSelectedFile();
    });

    // Drag and Drop
    dropzone.addEventListener('click', () => fileInput.click());

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('drag-over');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('drag-over');
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) handleFileSelect(files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) handleFileSelect(e.target.files[0]);
    });

    function handleFileSelect(file) {
        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatBytes(file.size);
        fileBanner.classList.remove('hidden');
        resetOutputState();
    }

    // Convert via Chunked Upload
    convertBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!selectedFile) return;

        convertBtn.disabled = true;
        convertBtn.classList.add('opacity-50', 'cursor-not-allowed');
        progressSection.classList.remove('hidden');
        resultSection.classList.add('hidden');
        errorSection.classList.add('hidden');

        const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB per chunk
        const totalChunks = Math.ceil(selectedFile.size / CHUNK_SIZE);
        const uploadId = 'upload_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
        currentTaskId = uploadId;

        try {
            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                if (currentTaskId !== uploadId) return; // Canceled

                const start = chunkIndex * CHUNK_SIZE;
                const end = Math.min(selectedFile.size, start + CHUNK_SIZE);
                const chunk = selectedFile.slice(start, end);

                const formData = new FormData();
                formData.append('chunk', chunk);
                formData.append('chunk_index', chunkIndex);
                formData.append('total_chunks', totalChunks);
                formData.append('upload_id', uploadId);
                formData.append('filename', selectedFile.name);

                const uploadPct = Math.round(((chunkIndex + 1) / totalChunks) * 50);
                progressBar.style.width = `${uploadPct}%`;
                progressPercent.textContent = `${uploadPct}%`;
                statusMessage.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-blue-600 mr-2"></i> Uploading chunk ${chunkIndex + 1} of ${totalChunks}...`;

                const response = await fetch('/api/upload_chunk', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.error || `Upload failed at chunk ${chunkIndex + 1}`);
                }

                const resData = await response.json();
                if (resData.status === 'uploaded') {
                    statusMessage.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-blue-600 mr-2"></i> Upload complete! Converting file...`;
                    pollProgress(resData.task_id);
                    return;
                }
            }
        } catch (err) {
            showError(err.message || 'Network error during upload.');
            resetConvertBtns();
        }
    });

    // Convert via Local File Path
    convertLocalBtn.addEventListener('click', async () => {
        const pathVal = localFilePath.value.trim();
        const formatVal = localFileFormat.value;

        if (!pathVal) {
            showError('Please enter a valid file path on your computer.');
            return;
        }

        convertLocalBtn.disabled = true;
        convertLocalBtn.classList.add('opacity-50', 'cursor-not-allowed');
        progressSection.classList.remove('hidden');
        resultSection.classList.add('hidden');
        errorSection.classList.add('hidden');

        progressBar.style.width = '5%';
        progressPercent.textContent = '5%';
        statusMessage.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-amber-600 mr-2"></i> Accessing local file...`;

        try {
            const response = await fetch('/api/convert_local_path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: pathVal, format_type: formatVal })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || 'Failed to locate local file.');
            }

            const data = await response.json();
            currentTaskId = data.task_id;
            pollProgress(data.task_id);

        } catch (err) {
            showError(err.message);
            resetConvertBtns();
        }
    });

    // Cancel Button Handler
    cancelBtn.addEventListener('click', async () => {
        if (!currentTaskId) return;

        cancelBtn.disabled = true;
        statusMessage.innerHTML = `<i class="fa-solid fa-ban text-rose-600 mr-2"></i> Canceling task...`;

        try {
            await fetch(`/api/cancel/${currentTaskId}`, { method: 'POST' });
        } catch (e) {
            console.error('Cancel request failed:', e);
        }

        if (pollInterval) clearInterval(pollInterval);
        showError('Conversion was canceled by user.');
        resetConvertBtns();
    });

    function pollProgress(taskId) {
        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/progress/${taskId}`);
                if (!res.ok) throw new Error('Task progress check failed');

                const task = await res.json();
                const pct = task.progress || 0;
                
                progressBar.style.width = `${pct}%`;
                progressPercent.textContent = `${pct}%`;

                if (task.message) {
                    statusMessage.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-blue-600 mr-2"></i> ${task.message}`;
                }

                if (task.status === 'completed') {
                    clearInterval(pollInterval);
                    showSuccess(taskId, task.filename, task.message);
                    resetConvertBtns();
                } else if (task.status === 'canceled') {
                    clearInterval(pollInterval);
                    showError('Conversion was canceled by user.');
                    resetConvertBtns();
                } else if (task.status === 'failed') {
                    clearInterval(pollInterval);
                    showError(task.message || task.error || 'Conversion failed.');
                    resetConvertBtns();
                }
            } catch (e) {
                console.error('Progress check error:', e);
            }
        }, 800);
    }

    function showSuccess(taskId, outFilename, msg) {
        progressSection.classList.add('hidden');
        resultSection.classList.remove('hidden');
        resultText.textContent = msg || `File converted to CSV successfully.`;
        downloadBtn.href = `/api/download/${taskId}`;
        downloadBtn.setAttribute('download', outFilename);
    }

    function showError(msg) {
        progressSection.classList.add('hidden');
        errorSection.classList.remove('hidden');
        errorMessage.textContent = msg;
    }

    function resetConvertBtns() {
        convertBtn.disabled = false;
        convertBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        convertLocalBtn.disabled = false;
        convertLocalBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        cancelBtn.disabled = false;
    }
});
