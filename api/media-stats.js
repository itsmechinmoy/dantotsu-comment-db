import fs from 'fs';
import path from 'path';
import readline from 'readline';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  try {
    const csvPath = path.join(process.cwd(), 'dantotsu_global_db.csv');
    
    if (!fs.existsSync(csvPath)) {
      return res.status(404).json({ 
        success: false, 
        error: 'Database not found. Run daily sync first.' 
      });
    }
    
    const stats = new Map();
    
    const fileStream = fs.createReadStream(csvPath);
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    
    let isFirstLine = true;
    let headers = [];
    
    for await (const line of rl) {
      if (isFirstLine) {
        headers = line.split('\t');
        isFirstLine = false;
        continue;
      }
      
      const values = line.split('\t');
      const row = {};
      headers.forEach((h, i) => { row[h] = values[i]; });
      
      if (row.deleted === '1') continue;
      
      const mediaId = row.media_id;
      if (!mediaId) continue;
      
      if (!stats.has(mediaId)) {
        stats.set(mediaId, {
          media_id: mediaId,
          total_comments: 0,
          reply_count: 0,
          top_level_comments: 0,
          unique_users: new Set()
        });
      }
      
      const record = stats.get(mediaId);
      record.total_comments++;
      record.unique_users.add(row.user_id);
      
      const parentId = row.parent_comment_id;
      if (parentId && parentId !== 'NULL' && parentId !== '') {
        record.reply_count++;
      } else {
        record.top_level_comments++;
      }
    }
    
    const result = Array.from(stats.values()).map(record => ({
      media_id: record.media_id,
      total_comments: record.total_comments,
      reply_count: record.reply_count,
      top_level_comments: record.top_level_comments,
      unique_users: record.unique_users.size
    }));
    
    result.sort((a, b) => b.total_comments - a.total_comments);
    
    res.status(200).json({ 
      success: true, 
      count: result.length,
      data: result.slice(0, 100)
    });
    
  } catch (error) {
    console.error('API Error:', error);
    res.status(500).json({ success: false, error: error.message });
  }
}
