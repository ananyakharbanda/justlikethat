#!/bin/bash

# Install certbot if not already installed
sudo yum install certbot -y

# Generate SSL certificate
sudo certbot certonly --standalone \
  -d api.zoppl.com \
  --email ananyakharbanda28@gmail.com \
  --agree-tos \
  --no-eff-email

# Create directories for SSL
sudo mkdir -p /etc/nginx/ssl

# Create symbolic links from Certbot certificates to Nginx expected location
sudo ln -sf /etc/letsencrypt/live/api.zoppl.com/fullchain.pem /etc/nginx/ssl/api.zoppl.com.crt
sudo ln -sf /etc/letsencrypt/live/api.zoppl.com/privkey.pem /etc/nginx/ssl/api.zoppl.com.key

# Create certificate renewal script
cat > /home/ec2-user/renew-certs.sh << 'EOF'
#!/bin/bash

# Log starting renewal process
echo "Starting certificate renewal process at $(date)" >> /home/ec2-user/cert_renewal.log

# Stop Docker containers
cd /home/ec2-user/justlikethat
docker-compose down

# Attempt to renew the certificates
sudo certbot renew --quiet

# Recreate symbolic links to ensure they point to the updated certificates
sudo ln -sf /etc/letsencrypt/live/api.zoppl.com/fullchain.pem /etc/nginx/ssl/api.zoppl.com.crt
sudo ln -sf /etc/letsencrypt/live/api.zoppl.com/privkey.pem /etc/nginx/ssl/api.zoppl.com.key

# Fix permissions if needed
sudo chmod -R 755 /etc/letsencrypt/live/
sudo chmod -R 755 /etc/letsencrypt/archive/

# Restart Docker containers
docker-compose up -d

# Log completion
echo "Certificate renewal completed at $(date)" >> /home/ec2-user/cert_renewal.log
EOF

# Make certificate renewal script executable
sudo chmod +x /home/ec2-user/renew-certs.sh

# Create cron job for certificate renewal
(crontab -l 2>/dev/null; echo "30 2,14 * * * /home/ec2-user/renew-certs.sh") | crontab -

echo "SSL setup complete!"