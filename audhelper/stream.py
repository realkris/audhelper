import numpy as np
from scipy.optimize import linear_sum_assignment as KM

import soundfile as sf

from .textgrid import TextGrid
from .read import ReadLargeWav

def textgrid_res(grid_file):
  text = open(grid_file).read()

  fid = TextGrid(text)
  
  for i, tier in enumerate(fid):
    res = tier.simple_transcript


  label_st = []
  label_ed = []
  labels = []
  for _st, _ed, _wd in res:
    _st = float(_st)
    _ed = float(_ed)

    label_st.append(_st)
    label_ed.append(_ed)

    if '救命' in _wd:
      labels.append(1)
    elif '报警' in _wd:
      labels.append(2)
    elif '抢劫' in _wd:
      labels.append(3)
    elif '杀人' in _wd:
      labels.append(4)
    else:
      labels.append(0)

  labels = np.array(labels)
  label_st = np.array(label_st)
  label_ed = np.array(label_ed)

  return labels, label_st, label_ed


def stream_test(f, model, interval=100):
  samples = model.samples
  samplerate = model.sample_rate
  overlap = samples - int(interval / 1000 * samplerate)
  steps = int(samples / samplerate * 1000 / interval)
  duration = int(samples / samplerate * 1000)

  # frames = sf.blocks(f, blocksize=samples, overlap=overlap)
  wav = ReadLargeWav(f)

  res = [np.zeros((1, model.num_classes))]

  cnt = 0
  while True:
    binary_data = wav.read(duration, interval)
    if binary_data is not None:
      frame = np.frombuffer(binary_data, dtype=np.short) / 32768.
      preds = model.infer(frame)

      res.append(preds)
    else:
      print(f'total {cnt * interval / 1000} s finished!')
      break
    
    cnt += 1
    if cnt % int(120 * 1000 / interval) == 0: print(f'{cnt * interval / 1000} s finished!')

  wav.close()

  return np.concatenate(res)


def report(res, _c, _s, gamma):
  """report alarms from result returned from stream_test"""
  _res = res.copy()
  # smooth
  for _, _scores in enumerate(_res):
    if _ == 0: continue

    _res[_, :] = _res[_, :] * gamma + _res[_-1, :] * (1 - gamma)

  reports = np.argmax(_res, axis=1)
  scores = np.max(_res, axis=1)

  pre_r = 0
  cum = 0
  cums = []
  alarms = []

  for r in reports:
    alarm = [0] * _res.shape[1]
    if r != 0 and (r == pre_r or _c == 0):
      if cum == _c:
        alarm[r] = 1
        cum = -_s
      else:
        alarm[0] = 1
        cum += 1
    else:
      alarm[0] = 1
      cum = max(0, cum-1)

    alarms.append(alarm)
    cums.append(cum)
    pre_r = r
  
  alarms = np.array(alarms)
  cums = np.array(cums)

  return alarms, cums


def alarm_eval(t1, t2, interval):
  cost_matrix = np.zeros((len(t1), len(t2)))

  for i in range(len(t1)):
    for j in range(len(t2)):
      diff = abs(t1[i] - t2[j])
      cost_matrix[i, j] = 1 / diff

  gt_idx, dt_idx = KM(cost_matrix, maximize=True)

  correct = 0
  for _g, _d in zip(gt_idx, dt_idx):
    if abs(t1[_g] - t2[_d]) <= interval:
      correct += 1
  
  return correct


def report_from_res(res_file, grid_file, interval=500, method='f1', word_index=1):
  # load labels and file
  labels, st, et = textgrid_res(grid_file)

  res = np.genfromtxt(res_file, delimiter=',')
  res = np.concatenate((res[[0], :], res[1::int(interval/100), ])) # interval for 200 ms
  best = 5
  _s = min(20, int(2000 / interval))

  for _g in np.arange(1, 11) / 10:
    for _c in range(11):
      alarms, _ = report(res, _c, _s, _g)
      
      alarms = alarms[:, word_index]
      time_alarms = np.arange(alarms.shape[0]) * interval / 1000

      t1 = st[labels == 1]
      t2 = time_alarms[alarms == 1]

      correct = alarm_eval(t1, t2, 2)
      recall = correct / (len(t1) + 1e-12) * 100
      precis = correct / (len(t2) + 1e-12) * 100
      f1 = 2 * precis * recall / (precis + recall + 1e-12)

      if method == 'f1':
        target = f1
      elif method == 'recall':
        target = recall
      elif method == 'precision':
        target = precis
      else:
        raise Exception(f'Wrong method {method} must be in f1/recall/precision!')

      if target > best - 5:
        if target > best:
          best = target
        print(f'word {word_index} on {method} - recall: {recall:.2f}, precision: {precis:.2f}, f1: {f1:.2f} @ {_c}, {_g}, {len(t1)} labels, {len(t2) - correct} false alarms.')

if __name__ == "__main__":
  pass