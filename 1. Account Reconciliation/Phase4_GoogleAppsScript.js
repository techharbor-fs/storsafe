/**
 * Phase 4 Manual Reconciliation - Google Apps Script Add-on
 * 
 * This script runs inside the Google Sheet and provides:
 * 1. Apply unique colors to selected cells directly
 * 2. Track color counter using Script Properties (no control sheet needed!)
 * 3. Python reads colors directly from the Unmatched sheet
 * 4. F9 hotkey support via Ctrl+Shift+1 macro
 * 
 * INSTALLATION:
 * 1. Open your Google Sheet
 * 2. Go to Extensions > Apps Script
 * 3. Delete any existing code
 * 4. Paste this entire script
 * 5. Save and authorize when prompted
 * 6. Refresh your spreadsheet
 * 7. You'll see a new "Phase 4" menu in the menu bar
 * 8. Go to Extensions > Macros > Manage macros
 * 9. Assign "applyColorToSelection" to Ctrl+Shift+1
 * 
 * USAGE:
 * 1. Run Python with --phase4-only flag
 * 2. In Google Sheets, select cells in Column F or G in "Unmatched" sheet
 * 3. Press F9 (Python sends Ctrl+Shift+1 to trigger coloring)
 * 4. Repeat for matching transactions
 * 5. When done, press F10 in Python to validate and process
 */

// Configuration
const UNMATCHED_SHEET_NAME = "Unmatched";
const COLOR_INDEX_PROPERTY = "phase4_color_index";

// Color palette (50 distinct HSV colors matching Python's palette)
const PHASE4_COLORS = [
  "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
  "#FFB3E6", "#E6B3FF", "#C9BAFF", "#FFB3D1", "#FFD1B3",
  "#D1FFB3", "#B3FFD1", "#B3D1FF", "#D1B3FF", "#FFD1E6",
  "#E6FFD1", "#D1E6FF", "#E6D1FF", "#FFEBD1", "#D1FFEB",
  "#EBD1FF", "#FFEBBE", "#EBFFBE", "#BEEBFF", "#FFBEEB",
  "#EBEBFF", "#FFEBEB", "#EBEBBE", "#BEFFEB", "#EBBEFF",
  "#FFC9BA", "#C9FFBA", "#BAC9FF", "#FFC9E6", "#E6FFC9",
  "#C9E6FF", "#E6C9FF", "#FFEBC9", "#C9FFEB", "#EBC9FF",
  "#FFD4BA", "#D4FFBA", "#BAD4FF", "#FFD4E6", "#E6FFD4",
  "#D4E6FF", "#E6D4FF", "#FFEBD4", "#D4FFEB", "#EBD4FF"
];

/**
 * Get current color index from Script Properties
 * This persists across script reloads (no control sheet needed!)
 */
function getCurrentColorIndex() {
  const properties = PropertiesService.getDocumentProperties();
  const value = properties.getProperty(COLOR_INDEX_PROPERTY);
  return value ? parseInt(value) : 0;
}

/**
 * Save color index to Script Properties
 */
function saveColorIndex(index) {
  const properties = PropertiesService.getDocumentProperties();
  properties.setProperty(COLOR_INDEX_PROPERTY, index.toString());
}

/**
 * Creates custom menu when spreadsheet opens
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Phase 4')
    .addItem('🎨 Apply Color to Selection', 'applyColorToSelection')
    .addItem('🔄 Reset Color Counter', 'resetColorCounter')
    .addSeparator()
    .addItem('ℹ️ Help', 'showHelp')
    .addToUi();
}

/**
 * Set up keyboard shortcut (optional - requires installable trigger)
 */
function onInstall() {
  onOpen();
}

/**
 * Apply next unique color to currently selected cells
 * This is the main function called by the user
 */
function applyColorToSelection() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const activeSheet = ss.getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  
  // Get ALL selected ranges (handles multi-cell selections)
  const selection = ss.getSelection();
  let rangesToColor = [];
  
  // Try to get all selected ranges
  const activeRangeList = selection.getActiveRangeList();
  if (activeRangeList) {
    rangesToColor = activeRangeList.getRanges();
  } else {
    // Fallback to single active range
    const singleRange = ss.getActiveRange();
    if (singleRange) {
      rangesToColor = [singleRange];
    }
  }
  
  // DEBUG: Log what we're seeing
  Logger.log(`Active sheet: ${activeSheet.getName()}`);
  Logger.log(`Number of ranges to color: ${rangesToColor.length}`);
  if (rangesToColor.length > 0) {
    rangesToColor.forEach((range, idx) => {
      Logger.log(`  Range ${idx + 1}: ${range.getA1Notation()}`);
    });
  }
  
  // Validation: Check if range is selected
  if (rangesToColor.length === 0) {
    ui.alert('⚠️ No cells selected!');
    return;
  }
  
  // Validation: Must be in Unmatched sheet
  if (activeSheet.getName() !== UNMATCHED_SHEET_NAME) {
    const unmatchedSheet = ss.getSheetByName(UNMATCHED_SHEET_NAME);
    if (unmatchedSheet) {
      ui.alert(
        `⚠️ Wrong Sheet!\n\n` +
        `You're currently in: "${activeSheet.getName()}"\n\n` +
        `Please:\n` +
        `1. Go to the "${UNMATCHED_SHEET_NAME}" sheet\n` +
        `2. Select cells in Column F or G\n` +
        `3. Then click "Apply Color to Selection" again`
      );
    } else {
      ui.alert(`⚠️ Cannot find "${UNMATCHED_SHEET_NAME}" sheet!`);
    }
    return;
  }
  
  // Validate all ranges are in columns F and G
  for (let i = 0; i < rangesToColor.length; i++) {
    const range = rangesToColor[i];
    const startCol = range.getColumn();
    const endCol = startCol + range.getNumColumns() - 1;
    
    if (startCol < 6 || endCol > 7) {
      ui.alert('⚠️ Please select cells only in Column F (Debit) and/or Column G (Credit)!');
      return;
    }
  }
  
  // Get current color index
  const currentColorIndex = getCurrentColorIndex();
  
  // Validation: Check if we have colors left
  if (currentColorIndex >= PHASE4_COLORS.length) {
    ui.alert('⚠️ Maximum color limit reached (50 colors)!\n\nPlease process current matches or reset the color counter.');
    return;
  }
  
  // Get the next color
  const color = PHASE4_COLORS[currentColorIndex];
  
  // Color ALL ranges in the selection
  let totalCells = 0;
  for (let i = 0; i < rangesToColor.length; i++) {
    const range = rangesToColor[i];
    const numRows = range.getNumRows();
    const numCols = range.getNumColumns();
    
    // Create 2D color array
    const colorArray = [];
    for (let row = 0; row < numRows; row++) {
      const rowArray = [];
      for (let col = 0; col < numCols; col++) {
        rowArray.push(color);
      }
      colorArray.push(rowArray);
    }
    
    // Apply color to this range
    range.setBackgrounds(colorArray);
    totalCells += numRows * numCols;
  }
  
  // Update color counter
  const newColorIndex = currentColorIndex + 1;
  saveColorIndex(newColorIndex);
  
  // Toast notification
  ss.toast(
    `Color #${newColorIndex} applied to ${totalCells} cell${totalCells > 1 ? 's' : ''} across ${rangesToColor.length} range${rangesToColor.length > 1 ? 's' : ''}`,
    '✅ Color Applied',
    2
  );
}

/**
 * Reset color counter to start over
 */
function resetColorCounter() {
  saveColorIndex(0);
  SpreadsheetApp.getUi().alert('✅ Color counter reset to 0!\n\nYou can now apply colors from the beginning.');
}

/**
 * Shows help information
 */
function showHelp() {
  const ui = SpreadsheetApp.getUi();
  ui.alert(
    'Phase 4 Manual Reconciliation Help',
    '🎨 HOW TO USE:\n\n' +
    '1. Run Python script with --phase4-only flag\n' +
    '2. Python will auto-highlight large transactions (≥ $10,000)\n' +
    '3. In Google Sheets:\n' +
    '   • Go to "Unmatched" sheet\n' +
    '   • Select cell(s) in Column F or G\n' +
    '   • Click "Phase 4" > "Apply Color to Selection"\n' +
    '   • Repeat for matching pairs (same color = matched)\n' +
    '4. When done coloring:\n' +
    '   • In Python terminal, press F10 to validate and process\n\n' +
    '📋 FEATURES:\n' +
    '• 50 unique colors available\n' +
    '• Instant coloring (no communication lag)\n' +
    '• Select single cell or entire range\n' +
    '• Color counter persists across sessions\n\n' +
    '❓ TROUBLESHOOTING:\n' +
    '• Out of colors? Click "Reset Color Counter"\n' +
    '• Make sure you\'re in the "Unmatched" sheet\n' +
    '• Only columns F and G can be colored\n\n' +
    '💡 NO CONTROL SHEET NEEDED - colors saved directly!',
    ui.ButtonSet.OK
  );
}

/**
 * Test function to verify Apps Script is working
 */
function testScript() {
  SpreadsheetApp.getUi().alert('✅ Google Apps Script is working!\n\nYou can now use Phase 4 functionality.');
}
