/**
 * OSINT Face Search - Frontend Application
 */

// DOM Elements
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const previewContainer = document.getElementById('preview-container');
const previewImage = document.getElementById('preview-image');
const previewFilename = document.getElementById('preview-filename');
const previewSize = document.getElementById('preview-size');
const searchBtn = document.getElementById('search-btn');
const clearBtn = document.getElementById('clear-btn');
const uploadSection = document.getElementById('upload-section');
const loadingSection = document.getElementById('loading-section');
const resultsSection = document.getElementById('results-section');
const progressBar = document.getElementById('progress-bar');
const resultsGrid = document.getElementById('results-grid');
const comparisonModal = document.getElementById('comparison-modal');
const modalClose = document.getElementById('modal-close');

// State
let currentFile = null;
let currentQueryHash = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    // Upload area click
    uploadArea.addEventListener('click', () => fileInput.click());
    
    // File input change
    fileInput.addEventListener('change', handleFileSelect);
    
    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
    
    // Search button
    searchBtn.addEventListener('click', startSearch);
    
    // Clear button
    clearBtn.addEventListener('click', clearPreview);
    
    // Back button
    document.getElementById('back-btn').addEventListener('click', goHome);
    
    // Modal close
    modalClose.addEventListener('click', closeModal);
    comparisonModal.addEventListener('click', (e) => {
        if (e.target === comparisonModal) closeModal();
    });
    
    // Sort select
    document.getElementById('sort-select').addEventListener('change', (e) => {
        sortResults(e.target.value);
    });
    
    // Export button
    document.getElementById('export-btn').addEventListener('click', exportResults);
}

// File Handling
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) handleFile(file);
}

function handleFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        return;
    }
    
    if (file.size > 10 * 1024 * 1024) {
        alert('File too large (max 10MB)');
        return;
    }
    
    currentFile = file;
    
    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewFilename.textContent = file.name;
        previewSize.textContent = formatFileSize(file.size);
        
        uploadArea.style.display = 'none';
        previewContainer.style.display = 'flex';
    };
    reader.readAsDataURL(file);
}

function clearPreview() {
    currentFile = null;
    fileInput.value = '';
    
    previewContainer.style.display = 'none';
    uploadArea.style.display = 'block';
    resultsSection.style.display = 'none';
}

function goHome() {
    currentFile = null;
    currentQueryHash = null;
    fileInput.value = '';
    
    uploadSection.style.display = 'block';
    loadingSection.style.display = 'none';
    resultsSection.style.display = 'none';
    previewContainer.style.display = 'none';
    uploadArea.style.display = 'block';
    
    resultsGrid.innerHTML = '';
}

// Search
async function startSearch() {
    if (!currentFile) return;
    
    // Show loading
    uploadSection.style.display = 'none';
    loadingSection.style.display = 'block';
    resultsSection.style.display = 'none';
    
    // Animate progress
    animateProgress();
    
    // Update engine statuses
    updateEngineStatus('active');
    
    try {
        const formData = new FormData();
        formData.append('file', currentFile);
        
        const response = await fetch('/api/search', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentQueryHash = data.query_hash;
            showResults(data);
        } else {
            alert(data.error || 'Search failed');
            clearPreview();
        }
    } catch (error) {
        console.error('Search error:', error);
        alert('Search failed: ' + error.message);
        clearPreview();
    }
}

function animateProgress() {
    let width = 0;
    const interval = setInterval(() => {
        width += Math.random() * 5;
        if (width > 95) width = 95;
        progressBar.style.width = width + '%';
    }, 1000);
    
    window.progressInterval = interval;
}

function updateEngineStatus(status) {
    document.querySelectorAll('.engine-status').forEach(el => {
        el.className = 'engine-status ' + status;
    });
}

// Results
function showResults(data) {
    // Clear loading
    clearInterval(window.progressInterval);
    progressBar.style.width = '100%';
    
    setTimeout(() => {
        loadingSection.style.display = 'none';
        resultsSection.style.display = 'block';
        
        // Update meta
        document.getElementById('results-count').textContent = 
            `${data.verified_matches} matches found`;
        document.getElementById('results-quality').textContent = 
            `Quality: ${(data.quality_score * 100).toFixed(0)}%`;
        document.getElementById('results-threshold').textContent = 
            `Threshold: ${data.threshold_used.toFixed(2)}`;
        
        // Update engine statuses
        if (data.engine_stats) {
            Object.entries(data.engine_stats).forEach(([engine, stats]) => {
                const el = document.querySelector(`[data-engine="${engine}"]`);
                if (el) {
                    el.className = 'engine-status ' + (stats.status === 'success' ? 'success' : 'error');
                }
            });
        }
        
        // Render results
        renderResults(data.results);
        
        // Update stats
        loadStats();
    }, 500);
}

function renderResults(results) {
    resultsGrid.innerHTML = '';
    
    if (results.length === 0) {
        resultsGrid.innerHTML = `
            <div class="no-results">
                <p>No matches found. Try a different image or lower threshold.</p>
            </div>
        `;
        return;
    }
    
    results.forEach(result => {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.onclick = () => showComparison(result);
        
        const similarityPercent = (result.similarity * 100).toFixed(1);
        const similarityClass = result.similarity > 0.7 ? 'high' : 
                               result.similarity > 0.5 ? 'medium' : 'low';
        
        card.innerHTML = `
            <img class="result-thumbnail" 
                 src="${result.thumbnail_url || '/static/placeholder.png'}" 
                 alt="Result"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22280%22 height=%22180%22><rect fill=%22%231a1a25%22 width=%22280%22 height=%22180%22/><text fill=%22%23555570%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22>No Preview</text></svg>'">
            <div class="result-info">
                <div class="result-header">
                    <span class="result-source">${extractDomain(result.url)}</span>
                    <span class="result-engine">${result.engine}</span>
                </div>
                <div class="result-title">${result.title || 'Image match'}</div>
                <div class="result-similarity">
                    <div class="similarity-bar">
                        <div class="similarity-fill ${similarityClass}" style="width: ${similarityPercent}%"></div>
                    </div>
                    <span class="similarity-value">${similarityPercent}%</span>
                </div>
            </div>
        `;
        
        resultsGrid.appendChild(card);
    });
}

function sortResults(criteria) {
    const cards = Array.from(resultsGrid.children);
    
    cards.sort((a, b) => {
        if (criteria === 'similarity') {
            return parseFloat(b.querySelector('.similarity-value').textContent) - 
                   parseFloat(a.querySelector('.similarity-value').textContent);
        } else if (criteria === 'engine') {
            return a.querySelector('.result-engine').textContent.localeCompare(
                   b.querySelector('.result-engine').textContent);
        }
        return 0;
    });
    
    cards.forEach(card => resultsGrid.appendChild(card));
}

// Comparison Modal
function showComparison(result) {
    document.getElementById('comp-query').src = previewImage.src;
    document.getElementById('comp-result').src = result.thumbnail_url || '';
    document.getElementById('comp-similarity').textContent = 
        (result.similarity * 100).toFixed(1) + '%';
    document.getElementById('comp-fill').style.width = 
        (result.similarity * 100) + '%';
    document.getElementById('comp-source').href = result.url;
    document.getElementById('comp-source').textContent = result.url;
    document.getElementById('comp-engine').textContent = result.engine;
    document.getElementById('comp-region').textContent = result.region_matched;
    
    // Store for feedback
    window.currentResult = result;
    
    comparisonModal.style.display = 'flex';
}

function closeModal() {
    comparisonModal.style.display = 'none';
}

// Feedback
document.getElementById('feedback-correct')?.addEventListener('click', () => {
    submitFeedback(true);
});

document.getElementById('feedback-incorrect')?.addEventListener('click', () => {
    submitFeedback(false);
});

async function submitFeedback(isCorrect) {
    if (!currentQueryHash || !window.currentResult) return;
    
    try {
        await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query_hash: currentQueryHash,
                result_url: window.currentResult.url,
                is_correct: isCorrect
            })
        });
        
        alert(isCorrect ? 'Marked as correct match' : 'Marked as false positive');
        closeModal();
    } catch (error) {
        console.error('Feedback error:', error);
    }
}

// Export
async function exportResults() {
    if (!currentQueryHash) return;
    
    try {
        const response = await fetch(`/api/export/json?query_hash=${currentQueryHash}`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `osint-search-${currentQueryHash.substring(0, 8)}.json`;
        a.click();
    } catch (error) {
        console.error('Export error:', error);
        alert('Export failed');
    }
}

// Stats
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('stat-images').textContent = stats.total_images || 0;
        document.getElementById('stat-searches').textContent = stats.total_searches || 0;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Utilities
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function extractDomain(url) {
    try {
        return new URL(url).hostname;
    } catch {
        return url.substring(0, 30);
    }
}
