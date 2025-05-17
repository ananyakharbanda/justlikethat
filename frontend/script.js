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

  // Function to replace Euro symbol with Dollar symbol and handle price format properly
  function formatPrice(priceString) {
    if (!priceString) return '';

    // Simply replace € with $
    return priceString.replace('€', '$');
  }

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
    // console.log('About to send request to backend');
    // console.log('File selected:', fileInput.files[0].name);

    // Use the correct URL to your backend (adjust as needed)
    const backendUrl = 'https://api.zoppl.com/api/fashion/find';
    // const backendUrl = 'http://localhost:5001/api/fashion/find';

    // Send image to backend with explicit mode
    fetch(backendUrl, {
      method: 'POST',
      body: formData,
      mode: 'cors', // Explicitly set CORS mode
    })
      .then((response) => {
        // console.log('Response status:', response.status);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.message || 'Server error occurred');
          });
        }
        return response.json();
      })
      .then((data) => {
        // console.log('Response data:', data);
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

        // console.log('Products data found:', products);

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
        // console.error('Error details:', error);
        // console.error('Error message:', error.message);
        // console.error('Error name:', error.name);

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

  // function displayProducts(products) {
  //   // Clear previous products
  //   productsGrid.innerHTML = '';

  //   // For debugging: Log all image URLs to check if H&M images have issues
  //   console.log('All product image URLs:');
  //   products.forEach((product, index) => {
  //     console.log(
  //       `Product ${index} (${product.retailer || 'unknown'}): ${
  //         product.image_url || 'No image'
  //       }`
  //     );
  //   });

  //   // Filter out products without valid images
  //   const validProducts = products.filter((product) => {
  //     // Check if we have an image URL - be more inclusive with H&M
  //     const imageUrl = product.image_url || '';

  //     // Skip products without images or with m3u8 video format
  //     // But accept any URL format that seems valid
  //     return imageUrl && !imageUrl.includes('.m3u8');
  //   });

  //   console.log(
  //     `Displaying ${validProducts.length} of ${
  //       products.length
  //     } products (filtered out ${
  //       products.length - validProducts.length
  //     } invalid images)`
  //   );

  //   validProducts.forEach((product) => {
  //     // Create product card
  //     const card = document.createElement('div');
  //     card.className = 'product-card';

  //     // Set data attributes for filtering
  //     if (product.attributes) {
  //       if (product.attributes.color) {
  //         card.setAttribute(
  //           'data-color',
  //           product.attributes.color.toLowerCase()
  //         );
  //       }
  //       if (product.attributes.length) {
  //         card.setAttribute(
  //           'data-length',
  //           product.attributes.length.toLowerCase()
  //         );
  //       }
  //       if (product.attributes.style) {
  //         card.setAttribute(
  //           'data-style',
  //           product.attributes.style.toLowerCase()
  //         );
  //       }
  //       if (product.attributes.material) {
  //         card.setAttribute(
  //           'data-material',
  //           product.attributes.material.toLowerCase()
  //         );
  //       }
  //     }

  //     // Check if product is available
  //     const isAvailable = product.availability
  //       ? product.availability.toLowerCase().includes('available')
  //       : true;
  //     const availabilityClass = isAvailable ? 'available' : 'unavailable';

  //     // Format the price properly
  //     const displayPrice = product.price ? formatPrice(product.price) : '';

  //     // Get image URL, ensure it has a protocol (fix for H&M images)
  //     let imageUrl = product.image_url || '';
  //     if (imageUrl && imageUrl.startsWith('//')) {
  //       imageUrl = 'https:' + imageUrl;
  //     }

  //     // For debugging
  //     console.log(
  //       `Adding product card for: ${product.name}, Image URL: ${imageUrl}`
  //     );

  //     // Build card HTML
  //     card.innerHTML = `
  //   <a href="${
  //     product.product_url || '#'
  //   }" class="product-link" target="_blank" rel="noopener noreferrer">
  //     <div class="retailer-tag ${product.retailer || 'unknown'}">${
  //       product.retailer || ''
  //     }</div>
  //     <div class="product-image">
  //       <img src="${imageUrl}" alt="${
  //       product.name || 'Product'
  //     }" onerror="this.onerror=null; this.src='placeholder.jpg'; console.error('Image failed to load:', this.alt);">
  //     </div>
  //     <div class="product-info">
  //       <h3 class="product-name">${product.name || 'Product'}</h3>
  //       <p class="product-price">${displayPrice}</p>
  //       <div class="product-attributes">
  //         ${
  //           product.attributes?.color
  //             ? `<span class="attribute">${product.attributes.color}</span>`
  //             : ''
  //         }
  //         ${
  //           product.attributes?.length
  //             ? `<span class="attribute">${product.attributes.length}</span>`
  //             : ''
  //         }
  //         ${
  //           product.attributes?.material
  //             ? `<span class="attribute">${product.attributes.material}</span>`
  //             : ''
  //         }
  //         ${
  //           product.attributes?.style
  //             ? `<span class="attribute">${product.attributes.style}</span>`
  //             : ''
  //         }
  //       </div>
  //       ${
  //         product.availability
  //           ? `<p class="availability ${availabilityClass}">${product.availability}</p>`
  //           : ''
  //       }
  //     </div>
  //   </a>`;

  //     productsGrid.appendChild(card);
  //   });

  //   // Show a message if no valid products were found
  //   if (validProducts.length === 0) {
  //     noResults.style.display = 'block';
  //   }
  // }

  function displayProducts(products) {
    // Clear previous products
    productsGrid.innerHTML = '';

    // Filter out products without valid images
    const validProducts = products.filter((product) => {
      // Check if we have an image URL
      const imageUrl = product.image_url || '';
      return imageUrl && !imageUrl.includes('.m3u8');
    });

    // console.log(`Displaying ${validProducts.length} products after filtering`);

    // Create cards for each product with INLINE STYLES for critical elements
    validProducts.forEach((product) => {
      // Create product card with inline background
      const card = document.createElement('div');
      card.className = 'product-card';
      card.style.background = 'white';
      card.style.position = 'relative';
      card.style.borderRadius = '8px';
      card.style.overflow = 'hidden';
      card.style.boxShadow = '0 4px 20px rgba(89, 55, 10, 0.08)';

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
      }

      // Get retailer
      const retailer = product.retailer || 'unknown';

      // Format price
      const displayPrice = product.price ? formatPrice(product.price) : '';

      // Format image URL
      let imageUrl = product.image_url || '';
      if (imageUrl && imageUrl.startsWith('//')) {
        imageUrl = 'https:' + imageUrl;
      }

      // Set availability
      const isAvailable = product.availability
        ? product.availability.toLowerCase().includes('available')
        : true;
      const availabilityClass = isAvailable ? 'available' : 'unavailable';

      // Create card content with all critical styles inline
      card.innerHTML = `
        <div style="position: absolute; top: 10px; right: 10px; padding: 3px 8px; font-size: 12px; text-transform: uppercase; border-radius: 4px; background-color: ${
          retailer === 'zara' ? '#000' : '#e50010'
        }; color: white; z-index: 10;">
          ${retailer}
        </div>
        
        <a href="${
          product.product_url || '#'
        }" style="display: block; text-decoration: none; color: inherit;" target="_blank">
          <div style="height: 320px; overflow: hidden;">
            <img src="${imageUrl}" alt="${
        product.name || 'Product'
      }" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.onerror=null; this.src='placeholder.jpg';">
          </div>
          
          <div style="background-color: white; padding: 20px;">
            <h3 style="font-size: 1rem; font-weight: 500; margin-bottom: 8px; color: #3a3a3a;">${
              product.name || 'Product'
            }</h3>
            <p style="font-size: 1.2rem; font-weight: 600; margin: 10px 0; color: #3a3a3a;">${displayPrice}</p>
            
            <div style="margin-top: 15px; display: flex; flex-wrap: wrap; gap: 8px;">
              ${
                product.attributes?.color
                  ? `<span style="background: #f0f0f0; color: #555; font-size: 0.8rem; padding: 4px 10px; border-radius: 20px;">${product.attributes.color}</span>`
                  : ''
              }
              ${
                product.attributes?.length
                  ? `<span style="background: #f0f0f0; color: #555; font-size: 0.8rem; padding: 4px 10px; border-radius: 20px;">${product.attributes.length}</span>`
                  : ''
              }
              ${
                product.attributes?.material
                  ? `<span style="background: #f0f0f0; color: #555; font-size: 0.8rem; padding: 4px 10px; border-radius: 20px;">${product.attributes.material}</span>`
                  : ''
              }
              ${
                product.attributes?.style
                  ? `<span style="background: #f0f0f0; color: #555; font-size: 0.8rem; padding: 4px 10px; border-radius: 20px;">${product.attributes.style}</span>`
                  : ''
              }
            </div>
            
            ${
              product.availability
                ? `<p style="font-size: 0.85rem; margin-top: 10px; color: ${
                    isAvailable ? '#2e7d32' : '#c62828'
                  };">${product.availability}</p>`
                : ''
            }
          </div>
        </a>
      `;

      productsGrid.appendChild(card);
    });

    // Show no results message if needed
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
    const retailers = new Set();
    const clothingTypes = new Set();

    products.forEach((product) => {
      // Track retailers for filtering
      if (product.retailer) {
        retailers.add(product.retailer.toLowerCase());
      }

      if (product.attributes) {
        if (product.attributes.color) {
          colors.add(product.attributes.color.toLowerCase());
        }
        if (product.attributes.length) {
          lengths.add(product.attributes.length.toLowerCase());
        }
        // Track clothing types
        if (product.attributes.clothing_type) {
          clothingTypes.add(product.attributes.clothing_type.toLowerCase());
        }
      }
    });
    // Check if there are skirts or dresses in the product collection
    const hasSkirtsOrDresses = Array.from(clothingTypes).some(
      (type) => type.includes('skirt') || type.includes('dress')
    );

    // Add retailer filters
    if (retailers.size > 0) {
      retailers.forEach((retailer) => {
        const capitalizedRetailer =
          retailer.charAt(0).toUpperCase() + retailer.slice(1);
        addFilter(capitalizedRetailer);
      });
    }

    // Only add length filters if there are skirts or dresses
    if (hasSkirtsOrDresses) {
      ['mini', 'midi', 'maxi'].forEach((length) => {
        if (lengths.has(length)) {
          const capitalizedLength =
            length.charAt(0).toUpperCase() + length.slice(1);
          addFilter(capitalizedLength);
        }
      });
    }
    // // Add length filters (mini, midi, maxi)
    // ['mini', 'midi', 'maxi'].forEach((length) => {
    //   if (lengths.has(length)) {
    //     const capitalizedLength =
    //       length.charAt(0).toUpperCase() + length.slice(1);
    //     addFilter(capitalizedLength);
    //   }
    // });

    // Add color filters
    if (colors.has('black')) {
      addFilter('Black');
    }

    // Add "Colored" filter if there are non-black colors
    if (colors.size > 1 || (colors.size === 1 && !colors.has('black'))) {
      addFilter('Colored');
    }
  }

  //
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

        // Filter by retailer (Zara, H&M)
        if (
          filterValue === 'zara' ||
          filterValue === 'h&m' ||
          filterValue === 'hm'
        ) {
          // Since we don't have data-retailer attributes, look for the retailer text in the card
          const retailerDiv = card.querySelector(
            'div[style*="position: absolute"]'
          );
          const retailerText = retailerDiv
            ? retailerDiv.textContent.trim().toLowerCase()
            : '';

          // Handle 'h&m' vs 'hm' check
          if (
            (filterValue === 'h&m' || filterValue === 'hm') &&
            (retailerText === 'h&m' || retailerText === 'hm')
          ) {
            card.style.display = 'block';
          } else if (retailerText === filterValue) {
            card.style.display = 'block';
          } else {
            card.style.display = 'none';
          }
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
          return;
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
          return;
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
          return;
        }

        // If we're here, the filter didn't match any category
        card.style.display = 'none';
      });
    });

    filterContainer.appendChild(button);
  }
});
