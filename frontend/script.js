document.addEventListener('DOMContentLoaded', function () {
  // Elements
  const fileInput = document.getElementById('fileInput');
  const imagePreview = document.getElementById('imagePreview');
  const previewContainer = document.querySelector('.preview-container');
  const uploadButton = document.getElementById('uploadButton');
  const errorMessage = document.getElementById('errorMessage');
  const loadingIndicator = document.querySelector('.loading-indicator');
  const clothingAnalysis = document.getElementById('clothingAnalysis');
  const analysisGrid = document.getElementById('analysisGrid');
  const productsGrid = document.getElementById('productsGrid');
  const resultsTitle = document.getElementById('resultsTitle');
  const filterContainer = document.getElementById('filterContainer');
  const noResults = document.getElementById('noResults');
  const uploadArea = document.querySelector('.upload-area');

  // Handle file selection
  fileInput.addEventListener('change', function () {
    const file = this.files[0];
    if (file) {
      if (!file.type.match('image.*')) {
        showError('Please select a valid image file (JPEG, PNG, GIF, WEBP)');
        resetPreview();
        return;
      }

      const reader = new FileReader();
      reader.onload = function (e) {
        imagePreview.src = e.target.result;
        previewContainer.style.display = 'block';
        uploadButton.disabled = false;
        errorMessage.style.display = 'none';
      };
      reader.readAsDataURL(file);
    } else {
      resetPreview();
    }
  });

  // Handle drag and drop
  uploadArea.addEventListener('dragover', function (e) {
    e.preventDefault();
    this.style.borderColor = '#000';
  });

  uploadArea.addEventListener('dragleave', function () {
    this.style.borderColor = '#ddd';
  });

  uploadArea.addEventListener('drop', function (e) {
    e.preventDefault();
    this.style.borderColor = '#ddd';

    if (e.dataTransfer.files.length) {
      const file = e.dataTransfer.files[0];
      if (file.type.match('image.*')) {
        fileInput.files = e.dataTransfer.files;

        const reader = new FileReader();
        reader.onload = function (e) {
          imagePreview.src = e.target.result;
          previewContainer.style.display = 'block';
          uploadButton.disabled = false;
          errorMessage.style.display = 'none';
        };
        reader.readAsDataURL(file);
      } else {
        showError('Please select a valid image file (JPEG, PNG, GIF, WEBP)');
      }
    }
  });

  // Handle upload button click
  uploadButton.addEventListener('click', function () {
    if (!fileInput.files.length) {
      showError('Please select an image first');
      return;
    }

    // Hide previous results if any
    resetResults();

    // Show loading indicator
    loadingIndicator.style.display = 'block';
    uploadButton.disabled = true;

    // Prepare form data
    const formData = new FormData();
    formData.append('image', fileInput.files[0]);

    // Log for debugging
    console.log('About to send request to backend');
    console.log('File selected:', fileInput.files[0].name);

    // Use the ABSOLUTE URL to your backend
    const backendUrl = 'https://api.zoppl.com:5001/api/fashion/find';

    // Send image to backend with explicit mode
    fetch(backendUrl, {
      method: 'POST',
      body: formData,
      mode: 'cors', // Explicitly set CORS mode
    })
      .then((response) => {
        console.log('Response status:', response.status);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.message || 'Server error occurred');
          });
        }
        return response.json();
      })
      .then((data) => {
        console.log('Response data:', data);
        // Hide loading indicator
        loadingIndicator.style.display = 'none';

        // Check for successful response
        if (data && data.status === false) {
          throw new Error(data.message || 'Failed to process image');
        }

        // In the backend, you directly return the scraper response
        // Let's try to determine where the clothing attributes and items are

        // For attributes, check different possible locations
        let clothingAttributes = null;
        if (data.clothing_attributes) {
          clothingAttributes = data.clothing_attributes;
        } else if (data.attributes) {
          clothingAttributes = data;
        } else if (data.clothing_type) {
          clothingAttributes = data;
        }

        if (clothingAttributes) {
          displayClothingAnalysis(clothingAttributes);
        }

        // For products, try different possible paths based on the scraper response
        let products = null;

        if (data.items && Array.isArray(data.items)) {
          // Original expected format
          products = data.items;
        } else if (data.response && Array.isArray(data.response)) {
          // Maybe the scraper uses "response" key
          products = data.response;
        } else if (data.products && Array.isArray(data.products)) {
          // Maybe the scraper uses "products" key
          products = data.products;
        } else if (data.results && Array.isArray(data.results)) {
          // Maybe the scraper uses "results" key
          products = data.results;
        } else if (Array.isArray(data)) {
          // Maybe the scraper returns an array directly
          products = data;
        }

        console.log('Products data found:', products);

        // Display products if available
        if (products && products.length > 0) {
          displayProducts(products);

          // Show filters
          createFilters(products);
          filterContainer.style.display = 'flex';

          // Show results title
          resultsTitle.style.display = 'block';
        } else {
          // Show no results message
          noResults.style.display = 'block';
        }

        // Re-enable upload button
        uploadButton.disabled = false;
      })
      .catch((error) => {
        // Hide loading indicator
        loadingIndicator.style.display = 'none';

        // Show detailed error in console
        console.error('Error details:', error);
        console.error('Error message:', error.message);
        console.error('Error name:', error.name);

        // Show error message to user
        showError(error.message || 'An error occurred');

        // Re-enable upload button
        uploadButton.disabled = false;
      });
  });

  // Helper functions
  function resetPreview() {
    imagePreview.src = '';
    previewContainer.style.display = 'none';
    uploadButton.disabled = true;
  }

  function resetResults() {
    clothingAnalysis.style.display = 'none';
    analysisGrid.innerHTML = '';
    productsGrid.innerHTML = '';
    resultsTitle.style.display = 'none';
    filterContainer.style.display = 'none';
    filterContainer.innerHTML = '';
    noResults.style.display = 'none';
  }

  function showError(message) {
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
  }

  function displayClothingAnalysis(data) {
    // Clear previous analysis
    analysisGrid.innerHTML = '';

    // Handle different response formats
    let clothingType = '';
    let attributes = {};

    if (data.clothing_type) {
      clothingType = data.clothing_type;
      attributes = data.attributes || {};
    } else if (data.attributes) {
      clothingType = data.attributes.clothing_type || '';
      attributes = data.attributes || {};
    }

    // Add clothing type
    if (clothingType) {
      addAnalysisItem('Item Type', clothingType);
    }

    // Add other attributes
    for (const [key, value] of Object.entries(attributes)) {
      if (key !== 'clothing_type' && value) {
        // Format the key (capitalize first letter, replace underscores with spaces)
        const formattedKey =
          key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
        addAnalysisItem(formattedKey, value);
      }
    }

    // Show analysis section
    clothingAnalysis.style.display = 'block';
  }

  function addAnalysisItem(label, value) {
    const item = document.createElement('div');
    item.className = 'analysis-item';

    const labelElement = document.createElement('div');
    labelElement.className = 'analysis-label';
    labelElement.textContent = label;

    const valueElement = document.createElement('div');
    valueElement.className = 'analysis-value';
    valueElement.textContent = value;

    item.appendChild(labelElement);
    item.appendChild(valueElement);

    analysisGrid.appendChild(item);
  }

  function displayProducts(products) {
    // Clear previous products
    productsGrid.innerHTML = '';

    // Filter out products without valid images
    const validProducts = products.filter((product) => {
      // Check if we have an image URL
      const imageUrl = product.image_url || '';

      // Skip products without images or with m3u8 video format
      return imageUrl && !imageUrl.includes('.m3u8');
    });

    console.log(
      `Displaying ${validProducts.length} of ${
        products.length
      } products (filtered out ${
        products.length - validProducts.length
      } invalid images)`
    );

    validProducts.forEach((product) => {
      // Create product card
      const card = document.createElement('div');
      card.className = 'product-card';

      // Set data attributes for filtering
      if (product.attributes) {
        if (product.attributes.color) {
          card.setAttribute(
            'data-color',
            product.attributes.color.toLowerCase()
          );
        }
        if (product.attributes.length) {
          card.setAttribute(
            'data-length',
            product.attributes.length.toLowerCase()
          );
        }
        if (product.attributes.style) {
          card.setAttribute(
            'data-style',
            product.attributes.style.toLowerCase()
          );
        }
        if (product.attributes.material) {
          card.setAttribute(
            'data-material',
            product.attributes.material.toLowerCase()
          );
        }
      }

      // Check if product is available
      const isAvailable = product.availability
        ? product.availability.toLowerCase().includes('available')
        : true;
      const availabilityClass = isAvailable ? 'available' : 'unavailable';

      // Build card HTML
      card.innerHTML = `
        <a href="${
          product.product_url || '#'
        }" class="product-link" target="_blank" rel="noopener noreferrer"></a>
        <div class="product-image">
          <img src="${product.image_url}" alt="${product.name || 'Product'}">
        </div>
        <div class="product-info">
          <h3 class="product-name">${product.name || 'Product'}</h3>
          <p class="product-price">${product.price || ''}</p>
          <div class="product-attributes">
            ${
              product.attributes?.color
                ? `<span class="attribute">${product.attributes.color}</span>`
                : ''
            }
            ${
              product.attributes?.length
                ? `<span class="attribute">${product.attributes.length}</span>`
                : ''
            }
            ${
              product.attributes?.material
                ? `<span class="attribute">${product.attributes.material}</span>`
                : ''
            }
            ${
              product.attributes?.style
                ? `<span class="attribute">${product.attributes.style}</span>`
                : ''
            }
          </div>
          ${
            product.availability
              ? `<p class="availability ${availabilityClass}">${product.availability}</p>`
              : ''
          }
        </div>
      `;

      productsGrid.appendChild(card);
    });

    // Show a message if no valid products were found
    if (validProducts.length === 0) {
      noResults.style.display = 'block';
    }
  }

  function createFilters(products) {
    // Clear existing filters
    filterContainer.innerHTML = '';

    // Add "All" filter
    addFilter('All', true);

    // Collect unique values for different attributes
    const colors = new Set();
    const lengths = new Set();

    products.forEach((product) => {
      if (product.attributes) {
        if (product.attributes.color) {
          colors.add(product.attributes.color.toLowerCase());
        }
        if (product.attributes.length) {
          lengths.add(product.attributes.length.toLowerCase());
        }
      }
    });

    // Add length filters (mini, midi, maxi)
    ['mini', 'midi', 'maxi'].forEach((length) => {
      if (lengths.has(length)) {
        addFilter(length.charAt(0).toUpperCase() + length.slice(1));
      }
    });

    // Add color filters (black + others)
    if (colors.has('black')) {
      addFilter('Black');
    }

    // Add "Colored" filter if there are non-black colors
    if (colors.size > 1 || (colors.size === 1 && !colors.has('black'))) {
      addFilter('Colored');
    }
  }

  function addFilter(text, isActive = false) {
    const button = document.createElement('button');
    button.className = 'filter-button' + (isActive ? ' active' : '');
    button.textContent = text;

    button.addEventListener('click', function () {
      // Update active state
      document.querySelectorAll('.filter-button').forEach((btn) => {
        btn.classList.remove('active');
      });
      this.classList.add('active');

      // Apply filter
      const filterValue = this.textContent.trim().toLowerCase();
      const cards = document.querySelectorAll('.product-card');

      cards.forEach((card) => {
        // Show all if "All" is selected
        if (filterValue === 'all') {
          card.style.display = 'block';
          return;
        }

        // Filter by length
        if (
          filterValue === 'mini' ||
          filterValue === 'midi' ||
          filterValue === 'maxi'
        ) {
          if (
            card.getAttribute('data-length') &&
            card.getAttribute('data-length').includes(filterValue)
          ) {
            card.style.display = 'block';
          } else {
            card.style.display = 'none';
          }
        }

        // Filter by color
        if (filterValue === 'black') {
          if (
            card.getAttribute('data-color') &&
            card.getAttribute('data-color').includes('black')
          ) {
            card.style.display = 'block';
          } else {
            card.style.display = 'none';
          }
        }

        // Show all non-black for "Colored" filter
        if (filterValue === 'colored') {
          if (
            card.getAttribute('data-color') &&
            !card.getAttribute('data-color').includes('black')
          ) {
            card.style.display = 'block';
          } else {
            card.style.display = 'none';
          }
        }
      });
    });

    filterContainer.appendChild(button);
  }
});
