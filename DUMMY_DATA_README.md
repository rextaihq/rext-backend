# Wrext Backend Dummy Data

This document describes the dummy data created for testing the frontend interface.

## 🎯 Overview

The dummy data provides a comprehensive dataset for testing all aspects of the Wrext workspace management system, including users, workspaces, brand voices, and all types of knowledge management.

## 📊 Data Summary

- **5 Users** - Test accounts with varied profiles
- **7 Workspaces** - Diverse workspace scenarios (5 new + 2 existing)
- **21 Web Knowledge** entries with realistic statuses
- **12 File Knowledge** entries across multiple file types
- **10 Text Knowledge** entries with rich content
- **8 Brand Voices** with complete metadata

## 👥 Test Users

All test users have the password: `password123`

| Email | Display Name | Role |
|-------|-------------|------|
| test@example.com | Test User | **Primary test account** |
| john.doe@example.com | John Doe | Workspace Owner |
| jane.smith@company.com | Jane Smith | Workspace Owner |
| mike.wilson@startup.io | Mike Wilson | Workspace Owner |
| admin@wrext.com | Admin User | System administrator |
| demo@wrext.com | Demo Account | Demonstration user |

## 🏢 Workspaces

### New Test Workspaces

1. **TechCorp Marketing Hub**
   - URL: https://techcorp.com
   - Owner: John Doe
   - Focus: Enterprise technology and digital transformation
   - Knowledge: 5 web articles, 3 files, 2 text pieces

2. **E-commerce Analytics**
   - URL: https://ecommerce-analytics.io
   - Owner: Jane Smith
   - Focus: E-commerce data analysis and customer insights
   - Knowledge: 4 web articles, 2 files, 2 text pieces

3. **Startup Growth Engine**
   - URL: https://startupgrowth.co
   - Owner: Mike Wilson
   - Focus: Startup growth and scaling strategies
   - Knowledge: 4 web articles, 3 files, 2 text pieces

4. **Health & Wellness Blog**
   - URL: https://healthwellness.blog
   - Owner: John Doe
   - Focus: Health, wellness, and lifestyle content
   - Knowledge: 4 web articles, 2 files, 2 text pieces

5. **FinTech Innovations**
   - URL: https://fintech-innovations.com
   - Owner: Jane Smith
   - Focus: Financial technology and blockchain
   - Knowledge: 4 web articles, 2 files, 2 text pieces

## 🌐 Web Knowledge Status Distribution

The web knowledge entries demonstrate various processing states:

- **13 Completed** - Fully processed with content statistics
- **3 Scraping** - Currently being processed
- **2 Processing** - Content extraction in progress
- **2 Failed** - Failed to scrape (for error handling testing)
- **1 Pending** - Waiting to be processed

## 📁 File Knowledge Types

Diverse file types for comprehensive testing:

- **5 PDF files** - Various technical documents and reports
- **2 Word documents** - Business documents and guides
- **2 Text files** - Plain text content and lists
- **1 Excel file** - Data analysis spreadsheet
- **1 Markdown file** - Technical documentation
- **1 PowerPoint** - Presentation template

**Total Size:** 25.27 MB across all files

## 🎯 Brand Voices

Each workspace has a complete brand voice profile including:

- **About** - Company/brand description
- **Customer Profile** - Target customer details
- **Selling Position** - Unique value proposition
- **Target Audience** - 4 different audience segments per workspace
- **Brand Voice** - 5 brand characteristics per workspace
- **Competitors** - 4 main competitors listed per workspace
- **Content Strategy** - Strategic content pillars

## 🧪 Testing Scenarios

### Frontend Interface Testing

1. **Workspace Management**
   - List workspaces in grid/list views
   - Navigate to individual workspace details
   - View workspace metadata and statistics

2. **Web Knowledge Management**
   - View web knowledge in various states
   - Test status indicators and progress displays
   - Add new URLs with validation
   - Delete web knowledge with confirmation

3. **File Knowledge Management**
   - Display files with correct type icons
   - Show file size and metadata
   - Handle different file formats
   - Upload and management workflows

4. **Text Knowledge Management**
   - Display text content with previews
   - Edit and manage text entries
   - Search within text content

5. **Brand Voice Display**
   - Show brand voice characteristics
   - Display target audience tags
   - List competitors and strategy pillars

6. **Search and Filtering**
   - Search across all knowledge types
   - Filter by status, type, workspace
   - Sort by various criteria

### Error Handling Testing

- **Failed Web Scraping** - Test error states and retry mechanisms
- **Invalid URLs** - Test validation and error messages
- **Empty States** - Test when no content is available
- **Loading States** - Test skeleton loaders and progress indicators

## 🚀 Running the Script

### Create All Dummy Data (Recommended)
```bash
cd /path/to/wrext-backend
source .venv/bin/activate
python create_all_dummy_data.py
```

This single comprehensive script creates all users, workspaces, brand voices, web knowledge, file knowledge, and text knowledge at once.

### Verify Data
```bash
cd /path/to/wrext-backend
source .venv/bin/activate
python verify_dummy_data.py
```

## 📋 Frontend Development Tips

1. **Realistic Data** - All URLs, company names, and content are realistic for authentic testing
2. **Varied States** - Web knowledge includes all possible status states for comprehensive UI testing
3. **Rich Metadata** - Brand voices and workspaces have complete data for testing all UI components
4. **Different Owners** - Workspaces are distributed among different users for multi-user scenarios
5. **Content Variety** - Text content ranges from short to long for responsive design testing

## 🔧 Customization

To add more dummy data or modify existing data:

1. Edit the data arrays in `create_all_dummy_data.py`
2. Run the script again (it will skip existing data)
3. Use `verify_dummy_data.py` to confirm changes

The script is idempotent - it won't create duplicates if run multiple times.

## ⚠️ Notes

- The script preserves any existing data in the database
- File paths in file knowledge are simulated (actual files don't exist)
- All URLs are real but content statistics are simulated
- Brand voice data is crafted to be realistic and varied for comprehensive testing

---

✨ **Happy Testing!** Your frontend now has a rich dataset to work with across all workspace management features.