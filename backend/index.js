const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { createClient } = require('@supabase/supabase-js');
const { OpenAI } = require('openai');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 5000;

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Clients
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
);

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

// System Prompt
const SYSTEM_PROMPT = `You are a helpful mentor for StarZopp. 
Answer in simple English. Explain step by step. 
Only use the provided website content to answer. 
If the answer is not in the provided content, say you don't know and guide the user on how they can find more info or ask a related question.
Be encouraging and use examples if possible.`;

/**
 * POST /api/chat
 * Handles RAG and returns AI response
 */
app.post('/api/chat', async (req, res) => {
  const { message, history = [] } = req.body;

  if (!message) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    // 1. Generate embedding for the question
    const embeddingResponse = await openai.embeddings.create({
      model: 'text-embedding-ada-002',
      input: message,
    });
    const queryEmbedding = embeddingResponse.data[0].embedding;

    // 2. Search Supabase for relevant content
    const { data: documents, error: searchError } = await supabase.rpc('match_documents', {
      query_embedding: queryEmbedding,
      match_threshold: 0.5,
      match_count: 5,
    });

    if (searchError) throw searchError;

    const contextText = documents.map(doc => doc.content).join('\n\n');

    // 3. Construct messages for OpenAI
    const messages = [
      { role: 'system', content: SYSTEM_PROMPT },
      ...history.slice(-6), // Include last 6 messages for context
      { role: 'user', content: `Context from website:\n${contextText}\n\nQuestion: ${message}` }
    ];

    // 4. Get response from OpenAI
    const chatResponse = await openai.chat.completions.create({
      model: 'gpt-4o', // or gpt-3.5-turbo
      messages: messages,
      temperature: 0.7,
    });

    const answer = chatResponse.choices[0].message.content;

    res.json({
      answer,
      context: documents.map(d => d.id) // Return IDs of docs used for reference
    });
  } catch (error) {
    console.error('Chat Error:', error);
    res.status(500).json({ error: 'Failed to generate response' });
  }
});

/**
 * POST /api/feedback
 * Stores feedback in Supabase
 */
app.post('/api/feedback', async (req, res) => {
  const { session_id, question, answer, feedback } = req.body;

  try {
    const { data, error } = await supabase
      .from('feedback')
      .insert([
        { session_id, question, answer, feedback }
      ]);

    if (error) throw error;
    res.json({ success: true, data });
  } catch (error) {
    console.error('Feedback Error:', error);
    res.status(500).json({ error: 'Failed to store feedback' });
  }
});

/**
 * POST /api/ingest
 * Manual ingestion of knowledge base
 */
app.post('/api/ingest', async (req, res) => {
  const { content } = req.body; // Expecting a big string or array

  if (!content) return res.status(400).json({ error: 'Content required' });

  try {
    // Split content into chunks (simple split by newline for now)
    const chunks = content.split('\n').filter(c => c.trim().length > 10);

    for (const chunk of chunks) {
      const embeddingResponse = await openai.embeddings.create({
        model: 'text-embedding-ada-002',
        input: chunk,
      });
      const embedding = embeddingResponse.data[0].embedding;

      await supabase.from('documents').insert({
        content: chunk,
        embedding: embedding
      });
    }

    res.json({ success: true, message: `Ingested ${chunks.length} chunks` });
  } catch (error) {
    console.error('Ingestion Error:', error);
    res.status(500).json({ error: 'Failed to ingest content' });
  }
});

app.listen(port, () => {
  console.log(`Backend running on http://localhost:${port}`);
});
