import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Divider,
  Drawer,
  Fab,
  FormControlLabel,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography
} from '@mui/material';
import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import SendRoundedIcon from '@mui/icons-material/SendRounded';
import {
  agentApply,
  agentChat,
  type AgentMessage,
  type AgentOperation,
  type AgentPendingAction
} from '../api';

interface AssistantProps {
  // Called after a plan is applied so the drive view can refresh.
  onApplied: () => void | Promise<void>;
}

interface SelectablePending extends AgentPendingAction {
  selected: boolean;
}

export function Assistant({ onApplied }: AssistantProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [pending, setPending] = useState<SelectablePending[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const conversation = messages.filter(
    (m) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string' && m.content.trim() !== ''
  );

  function toolResult(action: AgentPendingAction, outcome: string): AgentMessage {
    return { role: 'tool', tool_call_id: action.tool_call_id, name: action.tool, content: outcome };
  }

  async function handleSend(): Promise<void> {
    const text = input.trim();
    if (!text || loading) return;
    const next: AgentMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(next);
    setInput('');
    setPending([]);
    setError('');
    setNotice('');
    setLoading(true);
    try {
      const response = await agentChat(next);
      setMessages(response.messages);
      setPending(response.pending_actions.map((action) => ({ ...action, selected: true })));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The assistant could not respond.');
    } finally {
      setLoading(false);
    }
  }

  function toggle(toolCallId: string): void {
    setPending((prev) =>
      prev.map((action) => (action.tool_call_id === toolCallId ? { ...action, selected: !action.selected } : action))
    );
  }

  function dismissPending(reason: string): void {
    setMessages((prev) => [...prev, ...pending.map((action) => toolResult(action, 'declined by user'))]);
    setPending([]);
    setNotice(reason);
  }

  async function handleApprove(): Promise<void> {
    const chosen = pending.filter((action) => action.selected);
    if (chosen.length === 0) {
      dismissPending('Nothing selected — proposal dismissed.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const operations: AgentOperation[] = chosen.map((action) => ({ tool: action.tool, ...action.args }));
      const result = await agentApply(operations);
      // Thread a tool result back for every proposed call so the conversation
      // stays valid if the user keeps chatting.
      const results = pending.map((action) => toolResult(action, action.selected ? 'applied' : 'declined by user'));
      setMessages((prev) => [...prev, ...results]);
      setPending([]);
      setNotice(`Applied ${result.applied} change${result.applied === 1 ? '' : 's'}.`);
      await onApplied();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not apply the changes.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Tooltip title="Reorganize with AI">
        <Fab
          color="primary"
          onClick={() => setOpen(true)}
          aria-label="Open the AI organizer"
          sx={{ position: 'fixed', bottom: 24, right: 24, zIndex: (theme) => theme.zIndex.drawer + 2 }}
        >
          <AutoAwesomeRoundedIcon />
        </Fab>
      </Tooltip>

      <Drawer
        anchor="right"
        open={open}
        onClose={() => setOpen(false)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 400 }, display: 'flex', flexDirection: 'column' } }}
      >
        <Stack direction="row" alignItems="center" spacing={1} sx={{ p: 1.5, borderBottom: 1, borderColor: 'divider' }}>
          <AutoAwesomeRoundedIcon color="primary" />
          <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>
            AI organizer
          </Typography>
          <IconButton onClick={() => setOpen(false)} aria-label="Close">
            <CloseRoundedIcon />
          </IconButton>
        </Stack>

        <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', p: 1.5 }}>
          {conversation.length === 0 && pending.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              Ask me to tidy your drive — for example, “Sort my files into folders by type” or “Group everything about
              my 2026 taxes together.” I’ll propose the changes and you approve them before anything happens.
            </Typography>
          )}

          <Stack spacing={1.25}>
            {conversation.map((message, index) => (
              <Paper
                key={index}
                elevation={0}
                sx={{
                  p: 1.25,
                  borderRadius: 2,
                  maxWidth: '90%',
                  alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                  bgcolor: message.role === 'user' ? 'primary.main' : 'action.hover',
                  color: message.role === 'user' ? 'primary.contrastText' : 'text.primary'
                }}
              >
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {message.content}
                </Typography>
              </Paper>
            ))}
          </Stack>

          {pending.length > 0 && (
            <Paper variant="outlined" sx={{ mt: 1.5, p: 1.25, borderRadius: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Proposed changes
              </Typography>
              <Stack spacing={0.25}>
                {pending.map((action) => (
                  <FormControlLabel
                    key={action.tool_call_id}
                    control={
                      <Checkbox size="small" checked={action.selected} onChange={() => toggle(action.tool_call_id)} />
                    }
                    label={<Typography variant="body2">{action.summary}</Typography>}
                  />
                ))}
              </Stack>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button variant="contained" size="small" onClick={handleApprove} disabled={loading}>
                  Approve &amp; apply
                </Button>
                <Button size="small" onClick={() => dismissPending('Proposal dismissed.')} disabled={loading}>
                  Reject
                </Button>
              </Stack>
            </Paper>
          )}

          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
              <CircularProgress size={22} />
            </Box>
          )}
        </Box>

        <Divider />
        <Box sx={{ p: 1.5 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
              {error}
            </Alert>
          )}
          {notice && (
            <Alert severity="success" sx={{ mb: 1 }} onClose={() => setNotice('')}>
              {notice}
            </Alert>
          )}
          <Stack direction="row" spacing={1} alignItems="flex-end">
            <TextField
              fullWidth
              multiline
              maxRows={4}
              size="small"
              placeholder="Ask the assistant to organize your files…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              disabled={loading}
            />
            <IconButton
              color="primary"
              onClick={() => void handleSend()}
              disabled={loading || input.trim() === ''}
              aria-label="Send"
            >
              <SendRoundedIcon />
            </IconButton>
          </Stack>
        </Box>
      </Drawer>
    </>
  );
}
