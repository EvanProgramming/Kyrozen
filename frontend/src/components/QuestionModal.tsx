import { useState, useEffect } from 'react';

export interface QuestionOption {
  label: string;
  value: string;
}

export interface QuestionData {
  question: string;
  options: QuestionOption[];
  allow_other?: boolean;
}

interface QuestionModalProps {
  open: boolean;
  question: QuestionData | null;
  onAnswer: (value: string) => void;
  onClose?: () => void;
}

export function QuestionModal({ open, question, onAnswer, onClose }: QuestionModalProps) {
  const [other, setOther] = useState('');

  useEffect(() => {
    if (open) {
      setOther('');
    }
  }, [open, question?.question]);

  if (!open || !question) return null;

  const canSubmitOther = other.trim().length > 0;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-warm-900/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 animate-[fadeIn_150ms_ease-out]">
        <h3 className="text-lg font-serif text-warm-900 mb-4">{question.question}</h3>

        <div className="space-y-2 mb-4">
          {question.options.map((option, index) => (
            <button
              key={index}
              onClick={() => onAnswer(option.value)}
              className="w-full text-left px-4 py-3 rounded-xl border border-warm-200 bg-warm-50 hover:bg-sky-50 hover:border-sky-200 text-warm-800 transition-colors"
            >
              {option.label}
            </button>
          ))}
        </div>

        {question.allow_other && (
          <div className="space-y-2">
            <label className="text-sm text-warm-500">其他</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={other}
                onChange={(e) => setOther(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canSubmitOther) {
                    onAnswer(other.trim());
                  }
                }}
                placeholder="请输入你的回答..."
                className="input flex-1"
              />
              <button
                onClick={() => onAnswer(other.trim())}
                disabled={!canSubmitOther}
                className="btn-primary disabled:opacity-50"
              >
                确认
              </button>
            </div>
          </div>
        )}

        {onClose && (
          <button
            onClick={onClose}
            className="mt-4 text-sm text-warm-500 hover:text-warm-700"
          >
            跳过
          </button>
        )}
      </div>
    </div>
  );
}
