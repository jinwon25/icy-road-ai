"""외부 가중치 없이 학습하는 소형 MLP 비교군. TabM·RealMLP 재현 구현은 아니다."""
import numpy as np
from sklearn.base import BaseEstimator,RegressorMixin


class LocalMLPRegressor(RegressorMixin,BaseEstimator):
    def __init__(self,epochs=40,width=128,depth=2,loss='huber',seed=20261024,threads=2,batch_size=2048):
        self.epochs=epochs;self.width=width;self.depth=depth;self.loss=loss
        self.seed=seed;self.threads=threads;self.batch_size=batch_size

    def _transform(self,x):
        a=np.asarray(x,dtype=np.float32)
        if a.ndim!=2 or a.shape[1]!=len(self.mean_) or np.isinf(a).any():raise ValueError('Invalid neural inputs')
        missing=np.isnan(a)
        values=np.where(missing,0,(a-self.mean_)/self.scale_).clip(-10,10)
        return np.concatenate([values,missing.astype(np.float32)],axis=1)

    def fit(self,x,y,sample_weight=None):
        import torch
        torch.set_num_threads(self.threads);torch.manual_seed(self.seed);torch.use_deterministic_algorithms(True)
        a=np.asarray(x,dtype=np.float32);target=np.asarray(y,dtype=np.float32)
        if a.ndim!=2 or not len(a) or target.shape!=(len(a),) or not np.isfinite(target).all() or np.isinf(a).any():
            raise ValueError('Finite targets and finite-or-missing training predictors required')
        self.feature_names_in_=np.array(list(x),dtype=object)
        count=np.isfinite(a).sum(axis=0).clip(min=1)
        self.mean_=(np.nansum(a,axis=0,dtype=np.float64)/count).astype(np.float32)
        self.scale_=np.sqrt(np.nansum((a-self.mean_)**2,axis=0,dtype=np.float64)/count).clip(min=1e-3).astype(np.float32)
        self.target_mean_=float(target.mean());self.target_scale_=max(float(target.std()),1e-3)
        xx=torch.from_numpy(self._transform(a));yy=torch.from_numpy((target-self.target_mean_)/self.target_scale_)
        w=np.ones(len(a),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        if w.shape!=(len(a),) or not np.isfinite(w).all() or (w<=0).any():raise ValueError('Positive finite weights required')
        ww=torch.from_numpy(w/w.mean());layers=[];width=xx.shape[1]
        for _ in range(self.depth):layers.extend([torch.nn.Linear(width,self.width),torch.nn.ReLU()]);width=self.width
        layers.append(torch.nn.Linear(width,1));self.model_=torch.nn.Sequential(*layers)
        optimizer=torch.optim.AdamW(self.model_.parameters(),lr=.002,weight_decay=.0003)
        scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=self.epochs,eta_min=.00002)
        self.loss_curve_=[]
        for epoch in range(self.epochs):
            self.model_.train();order=torch.randperm(len(xx));total=0.
            for index in order.split(self.batch_size):
                optimizer.zero_grad(set_to_none=True);pred=self.model_(xx[index]).squeeze(-1)
                if self.loss=='mae':loss=(pred-yy[index]).abs()
                elif self.loss=='mse':loss=(pred-yy[index]).square()
                elif self.loss=='huber':loss=torch.nn.functional.smooth_l1_loss(pred,yy[index],beta=1.5/self.target_scale_,reduction='none')
                else:raise ValueError('Unknown neural loss')
                value=(loss*ww[index]).mean();value.backward();torch.nn.utils.clip_grad_norm_(self.model_.parameters(),5.)
                optimizer.step();total+=float(value.detach())*len(index)
            scheduler.step();self.loss_curve_.append(total/len(xx))
            if (epoch+1)%10==0:print('MLP epoch',epoch+1,'training loss',round(self.loss_curve_[-1],6),flush=True)
        self.model_.eval();return self

    def predict(self,x):
        import torch
        if list(x)!=list(self.feature_names_in_):raise ValueError('Neural feature order mismatch')
        self.model_.eval();parts=[]
        with torch.inference_mode():
            for batch in torch.from_numpy(self._transform(x)).split(self.batch_size):parts.append(self.model_(batch).squeeze(-1).numpy())
        return np.concatenate(parts)*self.target_scale_+self.target_mean_
