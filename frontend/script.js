// State Management
let state = {
    categories: [],
    currentStep: 1,
    filterMode: 'include',
    selectedCategories: new Set(),
    collapsedSections: new Set(),
    searchTerm: '',
    credentials: {
        url: '',
        username: '',
        password: '',
        includeVod: false
    }
};

// DOM Elements
const elements = {
    steps: {
        1: document.getElementById('step1'),
        2: document.getElementById('step2'),
        3: document.getElementById('step3')
    },
    loading: document.getElementById('loading'),
    loadingText: document.getElementById('loadingText'),
    categoryChips: document.getElementById('categoryChips'),
    selectionCounter: document.getElementById('selectionCounter'),
    selectionText: document.getElementById('selectionText'),
    confirmationModal: document.getElementById('confirmationModal'),
    modalSummary: document.getElementById('modalSummary'),
    results: document.getElementById('results'),
    downloadLink: document.getElementById('finalDownloadLink'),
    searchInput: document.getElementById('categorySearch'),
    apiBuilderModal: document.getElementById('apiBuilderModal'),
    generatedApiUrl: document.getElementById('generatedApiUrl'),
    generatedCliCommand: document.getElementById('generatedCliCommand'),
    cliCommandContainer: document.getElementById('cliCommandContainer')
};

// Step Navigation
function showStep(stepNumber) {
    // Hide all steps
    Object.values(elements.steps).forEach(step => step.classList.remove('active'));
    // Show target step
    elements.steps[stepNumber].classList.add('active');
    state.currentStep = stepNumber;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goBackToStep1() {
    showStep(1);
}

function showLoading(message = 'Loading...') {
    // Hide all steps
    Object.values(elements.steps).forEach(step => step.classList.remove('active'));
    elements.loading.style.display = 'block';
    elements.loadingText.textContent = message;
}

function hideLoading() {
    elements.loading.style.display = 'none';
}

function showError(message) {
    elements.results.innerHTML = `
        <div class="alert alert-error">
            <span>⚠️</span> ${message}
        </div>
    `;
    setTimeout(() => {
        elements.results.innerHTML = '';
    }, 5000);
}

// Data Fetching
async function loadCategories() {
    const url = document.getElementById('url').value.trim();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const includeVod = document.getElementById('includeVod').checked;

    if (!url || !username || !password) {
        showError('Please fill in all required fields');
        return;
    }

    // Update state
    state.credentials = { url, username, password, includeVod };

    showLoading('Connecting to IPTV service...');
    document.getElementById('loadBtn').disabled = true;

    try {
        const params = new URLSearchParams({
            url, username, password,
            include_vod: includeVod
        });

        const response = await fetch(`/categories?${params}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to fetch categories');
        }

        state.categories = data;
        state.searchTerm = '';
        elements.searchInput.value = '';
        renderCategories();
        showStep(2);

    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
        showStep(1);
    } finally {
        hideLoading();
        document.getElementById('loadBtn').disabled = false;
    }
}

// Category Rendering
function renderCategories() {
    elements.categoryChips.innerHTML = '';
    // Preserve selection if just re-rendering, but currently we usually re-fetch on Step 1 -> 2.
    // If we want to support search without re-rendering everything, we can just hide elements.
    // But initially, we render all.

    // Group categories
    const groups = {
        live: [],
        vod: [],
        series: []
    };

    state.categories.forEach(cat => {
        const type = cat.content_type || 'live';
        if (groups[type]) groups[type].push(cat);
    });

    const sectionConfig = [
        { key: 'live', title: '📺 Live Channels' },
        { key: 'vod', title: '🎬 Movies' },
        { key: 'series', title: '🍿 TV Series' }
    ];

    sectionConfig.forEach(section => {
        const cats = groups[section.key];
        if (cats && cats.length > 0) {
            // Wrapper
            const wrapper = document.createElement('div');
            wrapper.className = 'category-group-wrapper';
            wrapper.dataset.section = section.key;

            // Header
            const header = document.createElement('div');
            header.className = 'category-section-header';
            if (state.collapsedSections.has(section.key)) {
                header.classList.add('collapsed');
            }
            header.dataset.section = section.key;

            // Header content
            header.innerHTML = `
                <h3>
                    <span class="chevron">▼</span>
                    ${section.title}
                    <span style="font-size:0.8em; opacity:0.7">(${cats.length})</span>
                </h3>
                <button class="btn-section-select-all" data-section="${section.key}">Select All</button>
            `;

            // Click handler for collapsing
            header.onclick = (e) => {
                // Prevent collapsing when clicking the select all button
                if (e.target.classList.contains('btn-section-select-all')) return;
                toggleSection(section.key, header);
            };

            wrapper.appendChild(header);

            // Grid
            const grid = document.createElement('div');
            grid.className = 'category-section';
            grid.dataset.section = section.key;
            if (state.collapsedSections.has(section.key)) {
                grid.classList.add('hidden');
            }

            cats.forEach(cat => {
                const chip = document.createElement('div');
                chip.className = 'category-chip';
                if (state.selectedCategories.has(cat.category_name)) {
                    chip.classList.add('selected');
                }
                chip.dataset.id = cat.category_id;
                chip.dataset.name = cat.category_name;
                chip.dataset.type = section.key;
                chip.title = cat.category_name;
                chip.textContent = cat.category_name;

                chip.onclick = () => toggleCategory(chip);
                grid.appendChild(chip);
            });

            wrapper.appendChild(grid);
            elements.categoryChips.appendChild(wrapper);
        }
    });

    setupSectionToggles();
    updateCounter();
}

function toggleCategory(chip) {
    const name = chip.dataset.name;
    if (state.selectedCategories.has(name)) {
        state.selectedCategories.delete(name);
        chip.classList.remove('selected');
    } else {
        state.selectedCategories.add(name);
        chip.classList.add('selected');
    }
    updateCounter();
}

function toggleSection(sectionKey, headerElement) {
    const grid = document.querySelector(`.category-section[data-section="${sectionKey}"]`);
    if (grid) {
        if (grid.classList.contains('hidden')) {
            grid.classList.remove('hidden');
            headerElement.classList.remove('collapsed');
            state.collapsedSections.delete(sectionKey);
        } else {
            grid.classList.add('hidden');
            headerElement.classList.add('collapsed');
            state.collapsedSections.add(sectionKey);
        }
    }
}

function setupSectionToggles() {
    document.querySelectorAll('.btn-section-select-all').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation(); // Prevent header collapse
            const section = e.target.dataset.section;
            // Get visible chips only if we want to respect search?
            // Usually "Select All" in a section implies all in that section,
            // but if search is active, maybe only visible ones.
            // Let's make it select all visible ones in that section.

            const chips = document.querySelectorAll(`.category-chip[data-type="${section}"]:not(.hidden)`);
            if (chips.length === 0) return;

            const allSelected = Array.from(chips).every(c => state.selectedCategories.has(c.dataset.name));

            chips.forEach(chip => {
                const name = chip.dataset.name;
                if (allSelected) {
                    state.selectedCategories.delete(name);
                    chip.classList.remove('selected');
                } else {
                    state.selectedCategories.add(name);
                    chip.classList.add('selected');
                }
            });
            updateCounter();
        };
    });
}

function clearSelection() {
    state.selectedCategories.clear();
    document.querySelectorAll('.category-chip').forEach(c => c.classList.remove('selected'));
    updateCounter();
}

function selectAllVisible() {
    const chips = document.querySelectorAll('.category-chip:not(.hidden)');
    chips.forEach(chip => {
        state.selectedCategories.add(chip.dataset.name);
        chip.classList.add('selected');
    });
    updateCounter();
}

function updateCounter() {
    const count = state.selectedCategories.size;
    const mode = document.querySelector('input[name="filterMode"]:checked').value;
    state.filterMode = mode;

    if (count === 0) {
        elements.selectionText.textContent = 'Select categories to include in your playlist';
        elements.selectionCounter.classList.remove('has-selection');
    } else {
        const action = mode === 'include' ? 'included' : 'excluded';
        elements.selectionText.innerHTML = `<strong>${count}</strong> categories will be ${action}`;
        elements.selectionCounter.classList.add('has-selection');
    }
}

function filterCategories(searchTerm) {
    state.searchTerm = searchTerm.toLowerCase();
    const chips = document.querySelectorAll('.category-chip');

    chips.forEach(chip => {
        const name = chip.dataset.name.toLowerCase();
        if (name.includes(state.searchTerm)) {
            chip.classList.remove('hidden');
        } else {
            chip.classList.add('hidden');
        }
    });

    // Also hide empty sections?
    document.querySelectorAll('.category-group-wrapper').forEach(wrapper => {
        const sectionKey = wrapper.dataset.section;
        const visibleChips = wrapper.querySelectorAll('.category-chip:not(.hidden)');

        if (visibleChips.length === 0) {
            wrapper.style.display = 'none';
        } else {
            wrapper.style.display = 'block';

            // Restore grid display if not collapsed
            const grid = wrapper.querySelector('.category-section');
            if (grid && !state.collapsedSections.has(sectionKey)) {
                // Grid should be visible (css handles grid display usually, but let's ensure)
                // The grid class .hidden handles it. If it doesn't have .hidden, it shows.
                // But wait, if we previously set style.display = 'none' on the grid directly...
            }
        }
    });
}

// API Builder
function showApiBuilder() {
    elements.apiBuilderModal.classList.add('active');
    updateApiUrl();
}

function closeApiBuilder() {
    elements.apiBuilderModal.classList.remove('active');
}

function updateApiUrl() {
    const apiType = document.querySelector('input[name="apiType"]:checked').value;
    const noStreamProxy = document.getElementById('apiNoStreamProxy').checked;
    const includeChannelId = document.getElementById('apiIncludeChannelId').checked;
    const enableCatchup = document.getElementById('apiEnableCatchup').checked;
    const proxyUrl = document.getElementById('apiProxyUrl').value.trim();
    const channelIdTag = document.getElementById('apiChannelIdTag').value.trim();

    // Toggle options visibility
    const m3uOptions = document.getElementById('m3uOptions');
    if (apiType === 'm3u') {
        m3uOptions.style.display = 'block';
    } else {
        m3uOptions.style.display = 'none';
    }

    const baseUrl = window.location.origin;
    const params = new URLSearchParams({
        url: state.credentials.url,
        username: state.credentials.username,
        password: state.credentials.password
    });

    if (state.credentials.includeVod) {
        // Backend expects 'include_vod'
        params.append('include_vod', 'true');
    }

    // Smart filtering: Omit filter params if they result in "All Content"
    const categories = Array.from(state.selectedCategories);
    const totalCategories = state.categories.length;

    // Logic for omitting params:
    // If Filter Mode is INCLUDE:
    //   - If ALL categories are selected -> Omit (Implicitly Include All)
    //   - If SOME categories are selected -> Include 'wanted_groups'
    //   - If NO categories are selected -> (Technically this would result in empty playlist, but usually implies 'Select something'.
    //     However, if we want to follow strict logic: Include 'wanted_groups=' (empty) or just don't append.
    //     Let's assume user wants *something*. If 0 selected in include mode, the URL will produce nothing anyway.

    // If Filter Mode is EXCLUDE:
    //   - If NO categories are selected -> Omit (Implicitly Exclude None = Include All)
    //   - If SOME categories are selected -> Include 'unwanted_groups'

    if (categories.length > 0) {
        if (state.filterMode === 'include') {
            // Only append if NOT all are selected
            if (categories.length < totalCategories) {
                params.append('wanted_groups', categories.join(','));
            }
        } else {
            // Exclude mode: Append unwanted groups
            params.append('unwanted_groups', categories.join(','));
        }
    } else {
        // Categories length is 0
        if (state.filterMode === 'include') {
            // Include mode + 0 selected = Empty playlist?
            // Or does user imply "All"? Usually UI starts empty.
            // If we omit, it defaults to ALL.
            // If user explicitly selected NOTHING in "Include Mode", they probably don't want ALL.
            // But for the API URL builder, let's assume if they selected nothing, they haven't configured filters, so defaulting to ALL (omitting) might be safer or adding an empty param.
            // But let's stick to the prompt: "we should not need to actually include all the categories, we should be able to just ommit it"
            // This implies the user selected ALL.

            // So if count == 0 in include mode, maybe they haven't started.
            // But if they selected ALL (via Select All), count == total.
            // The check `categories.length < totalCategories` above handles the "Selected All" case for Include mode.
        }
    }

    if (apiType === 'm3u') {
        if (noStreamProxy) params.append('nostreamproxy', 'true');
        if (includeChannelId) params.append('include_channel_id', 'true');
        if (enableCatchup) params.append('enable_catchup', 'true');
        if (proxyUrl) params.append('proxy_url', proxyUrl);
        if (channelIdTag) params.append('channel_id_tag', channelIdTag);

        elements.generatedApiUrl.textContent = `${baseUrl}/m3u?${params.toString()}`;
        elements.cliCommandContainer.style.display = 'block';
        elements.generatedCliCommand.textContent = buildCliCommand({
            wantedGroups: params.get('wanted_groups'),
            unwantedGroups: params.get('unwanted_groups'),
            includeVod: params.get('include_vod') === 'true',
            noStreamProxy,
            includeChannelId,
            enableCatchup,
            proxyUrl,
            channelIdTag,
        });
    } else {
        if (proxyUrl) params.append('proxy_url', proxyUrl);
        elements.generatedApiUrl.textContent = `${baseUrl}/xmltv?${params.toString()}`;
        elements.cliCommandContainer.style.display = 'none';
    }
}

function buildCliCommand(opts) {
    // Shell-escape a single argument (single-quote wrap, escape embedded quotes)
    const sh = (s) => `'${String(s).replace(/'/g, "'\\''")}'`;
    const parts = ['python', 'cli.py'];
    if (opts.wantedGroups) parts.push('--wanted-groups', sh(opts.wantedGroups));
    if (opts.unwantedGroups) parts.push('--unwanted-groups', sh(opts.unwantedGroups));
    if (opts.includeVod) parts.push('--include-vod');
    if (opts.enableCatchup) parts.push('--enable-catchup');
    if (opts.includeChannelId) parts.push('--include-channel-id');
    if (opts.channelIdTag && opts.channelIdTag !== 'channel-id') {
        parts.push('--channel-id-tag', sh(opts.channelIdTag));
    }
    if (opts.noStreamProxy) parts.push('--no-stream-proxy');
    if (opts.proxyUrl) parts.push('--proxy-url', sh(opts.proxyUrl));
    parts.push('-o', 'playlist.m3u');
    return parts.join(' ');
}

function copyCliCommand() {
    const cmd = elements.generatedCliCommand.textContent;
    navigator.clipboard.writeText(cmd).then(() => {
        const btn = document.querySelector('#cliCommandContainer .btn-copy');
        const originalText = btn.textContent;
        btn.textContent = '✅';
        setTimeout(() => btn.textContent = originalText, 1500);
    });
}

function copyApiUrl() {
    const url = elements.generatedApiUrl.textContent;
    navigator.clipboard.writeText(url).then(() => {
        const btn = document.querySelector('.btn-copy');
        const originalText = btn.textContent;
        btn.textContent = '✅';
        setTimeout(() => btn.textContent = originalText, 1500);
    });
}

// Confirmation & Generation
function showConfirmation() {
    const count = state.selectedCategories.size;
    elements.confirmationModal.classList.add('active');

    // Check filter mode again just in case
    state.filterMode = document.querySelector('input[name="filterMode"]:checked').value;
    const action = state.filterMode === 'include' ? 'Include' : 'Exclude';
    const desc = count === 0 ? 'All Categories' : `${action} ${count} categories`;

    // Check for TV Series selection
    let seriesWarning = '';
    const hasSeriesSelected = Array.from(state.selectedCategories).some(name => {
        // Find category object to check type
        const cat = state.categories.find(c => c.category_name === name);
        return cat && cat.content_type === 'series';
    });

    if (state.credentials.includeVod && (state.filterMode === 'include' && hasSeriesSelected)) {
         seriesWarning = `
            <div class="alert alert-warning" style="margin-top: 1rem; font-size: 0.85rem; align-items: flex-start;">
                <span style="font-size: 1.2rem; line-height: 1;">⚠️</span>
                <div>
                    <strong>TV Series Selected</strong><br>
                    Fetching episode data is limited by the Xtream API speed.<br>
                    <span style="opacity: 0.9">Processing may take a significant amount of time (minutes to hours) depending on the number of series.</span>
                </div>
            </div>
        `;
    }

    elements.modalSummary.innerHTML = `
        <div class="summary-row">
            <span class="summary-label">Service URL</span>
            <span class="summary-value" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${state.credentials.url}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Content</span>
            <span class="summary-value">${state.credentials.includeVod ? 'Live TV + VOD' : 'Live TV Only'}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Filter Config</span>
            <span class="summary-value">${desc}</span>
        </div>
        ${seriesWarning}
    `;
}

function closeModal() {
    elements.confirmationModal.classList.remove('active');
}

async function confirmGeneration() {
    closeModal();
    showLoading('Generating Playlist...');

    const requestData = {
        ...state.credentials,
        nostreamproxy: true,
        include_vod: state.credentials.includeVod
    };

    // Remove the original camelCase property to avoid confusion/duplication
    delete requestData.includeVod;

    const categories = Array.from(state.selectedCategories);
    if (categories.length > 0) {
        if (state.filterMode === 'include') {
            requestData.wanted_groups = categories.join(',');
        } else {
            requestData.unwanted_groups = categories.join(',');
        }
    }

    try {
        // Decide method based on payload size
        const usePost = categories.length > 10 || JSON.stringify(requestData).length > 1500;

        let response;
        if (usePost) {
            response = await fetch('/m3u', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
        } else {
            const params = new URLSearchParams(requestData);
            response = await fetch(`/m3u?${params}`);
        }

        if (!response.ok) throw new Error('Generation failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        elements.downloadLink.href = url;
        elements.downloadLink.download = state.credentials.includeVod ? 'Full_Playlist.m3u' : 'Live_Playlist.m3u';

        showStep(3);

    } catch (error) {
        console.error(error);
        showError('Failed to generate playlist. Please check your inputs and try again.');
        showStep(2);
    } finally {
        hideLoading();
    }
}

function startOver() {
    // Reset inputs
    document.getElementById('url').value = '';
    document.getElementById('username').value = '';
    document.getElementById('password').value = '';
    document.getElementById('includeVod').checked = false;

    // Clear state
    state.categories = [];
    state.selectedCategories.clear();
    state.searchTerm = '';
    elements.searchInput.value = '';

    showStep(1);
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Filter mode change
    document.querySelectorAll('input[name="filterMode"]').forEach(radio => {
        radio.addEventListener('change', updateCounter);
    });

    // Search input
    elements.searchInput.addEventListener('input', (e) => {
        filterCategories(e.target.value);
    });

    // Close modal on outside click
    elements.confirmationModal.addEventListener('click', (e) => {
        if (e.target === elements.confirmationModal) closeModal();
    });

    elements.apiBuilderModal.addEventListener('click', (e) => {
        if (e.target === elements.apiBuilderModal) closeApiBuilder();
    });

    // Input trim handlers
    document.querySelectorAll('input').forEach(input => {
        input.addEventListener('blur', (e) => {
            if(e.target.type !== 'checkbox' && e.target.type !== 'radio') {
                e.target.value = e.target.value.trim();
            }
        });
    });
});
